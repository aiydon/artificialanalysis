from __future__ import annotations

import csv
import json
import logging
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    detail TEXT
);

CREATE TABLE IF NOT EXISTS dataset_runs (
    run_id INTEGER NOT NULL REFERENCES runs(id),
    dataset TEXT NOT NULL,
    ok INTEGER NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    PRIMARY KEY (run_id, dataset)
);

CREATE TABLE IF NOT EXISTS observations (
    run_id INTEGER NOT NULL REFERENCES runs(id),
    dataset TEXT NOT NULL,
    record_key TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (run_id, dataset, record_key)
);

CREATE INDEX IF NOT EXISTS observations_dataset_run
    ON observations (dataset, run_id);

CREATE VIEW IF NOT EXISTS latest AS
SELECT o.dataset, o.record_key, o.observed_at, o.payload
FROM observations AS o
JOIN (
    SELECT dataset, MAX(run_id) AS run_id
    FROM dataset_runs
    WHERE ok = 1
    GROUP BY dataset
) AS r ON r.dataset = o.dataset AND r.run_id = o.run_id;
"""


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten nested objects to dot-notation keys; lists become JSON text."""
    flat: dict[str, Any] = {}
    for key, item in value.items():
        name = f"{prefix}{key}"
        if isinstance(item, dict):
            flat.update(flatten(item, f"{name}."))
        elif isinstance(item, (list, tuple)):
            flat[name] = json.dumps(item, ensure_ascii=False)
        else:
            flat[name] = item
    return flat


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def begin(self, started_at: str) -> int:
        with self._db:
            cursor = self._db.execute("INSERT INTO runs (started_at) VALUES (?)", (started_at,))
        return int(cursor.lastrowid)

    def add_dataset(
        self,
        run_id: int,
        dataset: str,
        rows: Iterable[tuple[str, dict[str, Any]]],
        observed_at: str,
    ) -> int:
        payloads = [
            (run_id, dataset, key, observed_at, json.dumps(record, ensure_ascii=False))
            for key, record in rows
        ]
        with self._db:
            self._db.executemany(
                "INSERT OR REPLACE INTO observations "
                "(run_id, dataset, record_key, observed_at, payload) VALUES (?, ?, ?, ?, ?)",
                payloads,
            )
            self._db.execute(
                "INSERT OR REPLACE INTO dataset_runs "
                "(run_id, dataset, ok, record_count) VALUES (?, ?, 1, ?)",
                (run_id, dataset, len(payloads)),
            )
        return len(payloads)

    def fail_dataset(self, run_id: int, dataset: str, error: str) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO dataset_runs "
                "(run_id, dataset, ok, record_count, error) VALUES (?, ?, 0, 0, ?)",
                (run_id, dataset, error),
            )

    def finish(self, run_id: int, finished_at: str, status: str, detail: Any) -> None:
        with self._db:
            self._db.execute(
                "UPDATE runs SET finished_at = ?, status = ?, detail = ? WHERE id = ?",
                (finished_at, status, json.dumps(detail, ensure_ascii=False), run_id),
            )

    def latest(self, dataset: str) -> list[sqlite3.Row]:
        return list(
            self._db.execute(
                "SELECT record_key, observed_at, payload FROM latest "
                "WHERE dataset = ? ORDER BY record_key",
                (dataset,),
            )
        )

    def stats(self) -> dict[str, Any]:
        run = self._db.execute(
            "SELECT id, started_at, finished_at, status FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        counts = {
            row["dataset"]: row["n"]
            for row in self._db.execute(
                "SELECT dataset, COUNT(*) AS n FROM latest GROUP BY dataset"
            )
        }
        return {"last_run": dict(run) if run else None, "latest_counts": counts}


def export_latest(store: Store, out_dir: Path, datasets: Iterable[str]) -> dict[str, int]:
    """Write the latest snapshot of each dataset as JSONL and flat CSV."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, int] = {}

    for dataset in datasets:
        rows = store.latest(dataset)
        if not rows:
            continue

        records = []
        flat_rows = []
        for row in rows:
            meta = {
                "_dataset": dataset,
                "_key": row["record_key"],
                "_observed_at": row["observed_at"],
            }
            payload = json.loads(row["payload"])
            records.append(payload | meta)
            flat_rows.append({**flatten(payload), **meta})

        columns = sorted({key for row in flat_rows for key in row})

        with (out_dir / f"{dataset}.jsonl").open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

        with (out_dir / f"{dataset}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(flat_rows)

        written[dataset] = len(rows)

    return written
