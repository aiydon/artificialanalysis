from __future__ import annotations

import csv
import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel

from .sources import Source

log = logging.getLogger(__name__)

SCHEMA_VERSION = 2

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    totals TEXT
);

CREATE TABLE IF NOT EXISTS dataset_runs (
    run_id INTEGER NOT NULL REFERENCES runs(id),
    dataset TEXT NOT NULL,
    ok INTEGER NOT NULL,
    records INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    unchanged INTEGER NOT NULL DEFAULT 0,
    removed INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    PRIMARY KEY (run_id, dataset)
);

CREATE TABLE IF NOT EXISTS records (
    dataset TEXT NOT NULL,
    record_key TEXT NOT NULL,
    payload TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    last_changed TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (dataset, record_key)
);

CREATE TABLE IF NOT EXISTS changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    dataset TEXT NOT NULL,
    record_key TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    change TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS changes_lookup ON changes (dataset, record_key, id);
CREATE INDEX IF NOT EXISTS changes_time ON changes (dataset, id);
CREATE INDEX IF NOT EXISTS records_active ON records (dataset, active);

CREATE VIEW IF NOT EXISTS latest AS
SELECT dataset, record_key, payload, first_seen, last_seen, last_changed
FROM records
WHERE active = 1;
"""


class DatasetStats(BaseModel):
    dataset: str
    ok: bool = True
    records: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    duration_ms: int = 0
    error: str | None = None


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


def canonical(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _archive_legacy(path: Path) -> None:
    if not path.exists():
        return
    try:
        connection = sqlite3.connect(path)
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        connection.close()
    except sqlite3.DatabaseError:
        return
    if "meta" in tables or "records" in tables:
        return
    backup = path.with_name(f"{path.stem}.legacy-{datetime.now():%Y%m%d%H%M%S}{path.suffix}")
    path.rename(backup)
    log.warning("archived pre-incremental database to %s", backup)


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        _archive_legacy(path)
        self.path = path
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def close(self) -> None:
        self._db.close()

    def begin(self, started_at: str) -> int:
        with self._db:
            cursor = self._db.execute("INSERT INTO runs (started_at) VALUES (?)", (started_at,))
        return int(cursor.lastrowid or 0)

    def apply_dataset(
        self,
        run_id: int,
        dataset: str,
        rows: Iterable[tuple[str, dict[str, Any]]],
        observed_at: str,
    ) -> DatasetStats:
        started = datetime.now(timezone.utc)
        unique = dict(rows)
        existing = {
            row["record_key"]: (row["content_hash"], bool(row["active"]), row["payload"])
            for row in self._db.execute(
                "SELECT record_key, content_hash, active, payload FROM records WHERE dataset = ?",
                (dataset,),
            )
        }

        inserted: list[tuple[str, str, str]] = []
        updated: list[tuple[str, str, str]] = []
        unchanged: list[str] = []
        changes: list[tuple[str, str, str, str]] = []
        seen: set[str] = set()

        for key, record in unique.items():
            seen.add(key)
            payload = canonical(record)
            digest = hashlib.sha256(payload.encode()).hexdigest()
            previous = existing.get(key)
            if previous is None:
                inserted.append((key, payload, digest))
                changes.append((key, observed_at, "insert", payload))
            elif previous[0] != digest or not previous[1]:
                updated.append((key, payload, digest))
                changes.append((key, observed_at, "update", payload))
            else:
                unchanged.append(key)

        removed = [
            (key, previous[2])
            for key, previous in existing.items()
            if key not in seen and previous[1]
        ]

        with self._db:
            self._db.executemany(
                "INSERT INTO records "
                "(dataset, record_key, payload, content_hash, first_seen, last_seen,"
                " last_changed, active) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                [
                    (dataset, key, payload, digest, observed_at, observed_at, observed_at)
                    for key, payload, digest in inserted
                ],
            )
            self._db.executemany(
                "INSERT INTO records "
                "(dataset, record_key, payload, content_hash, first_seen, last_seen,"
                " last_changed, active) VALUES (?, ?, ?, ?, ?, ?, ?, 1) "
                "ON CONFLICT(dataset, record_key) DO UPDATE SET "
                " payload = excluded.payload, content_hash = excluded.content_hash,"
                " last_seen = excluded.last_seen, last_changed = excluded.last_changed,"
                " active = 1",
                [
                    (dataset, key, payload, digest, observed_at, observed_at, observed_at)
                    for key, payload, digest in updated
                ],
            )
            self._db.executemany(
                "UPDATE records SET last_seen = ? WHERE dataset = ? AND record_key = ?",
                [(observed_at, dataset, key) for key in unchanged],
            )
            for key, payload in removed:
                self._db.execute(
                    "UPDATE records SET active = 0, last_changed = ? "
                    "WHERE dataset = ? AND record_key = ?",
                    (observed_at, dataset, key),
                )
                changes.append((key, observed_at, "remove", payload))
            self._db.executemany(
                "INSERT INTO changes (run_id, dataset, record_key, observed_at, change, payload) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(run_id, dataset, *change) for change in changes],
            )

        duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        stats = DatasetStats(
            dataset=dataset,
            records=len(unique),
            inserted=len(inserted),
            updated=len(updated),
            unchanged=len(unchanged),
            removed=len(removed),
            duration_ms=duration_ms,
        )
        self._save_dataset_run(run_id, stats)
        return stats

    def _save_dataset_run(self, run_id: int, stats: DatasetStats) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO dataset_runs "
                "(run_id, dataset, ok, records, inserted, updated, unchanged, removed,"
                " duration_ms, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    stats.dataset,
                    int(stats.ok),
                    stats.records,
                    stats.inserted,
                    stats.updated,
                    stats.unchanged,
                    stats.removed,
                    stats.duration_ms,
                    stats.error,
                ),
            )

    def fail_dataset(self, run_id: int, dataset: str, error: str) -> DatasetStats:
        stats = DatasetStats(dataset=dataset, ok=False, error=error)
        self._save_dataset_run(run_id, stats)
        return stats

    def finish(self, run_id: int, finished_at: str, status: str, totals: dict[str, Any]) -> None:
        with self._db:
            self._db.execute(
                "UPDATE runs SET finished_at = ?, status = ?, totals = ? WHERE id = ?",
                (finished_at, status, json.dumps(totals, ensure_ascii=False), run_id),
            )

    def latest(self, dataset: str) -> list[sqlite3.Row]:
        return list(
            self._db.execute(
                "SELECT record_key, payload, first_seen, last_seen, last_changed "
                "FROM latest WHERE dataset = ? ORDER BY record_key",
                (dataset,),
            )
        )

    def history(self, dataset: str, key: str, limit: int = 50) -> list[sqlite3.Row]:
        return list(
            self._db.execute(
                "SELECT observed_at, change, payload FROM changes "
                "WHERE dataset = ? AND record_key = ? ORDER BY id DESC LIMIT ?",
                (dataset, key, limit),
            )
        )

    def stats(self) -> dict[str, Any]:
        run = self._db.execute(
            "SELECT id, started_at, finished_at, status, totals FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        datasets = [
            dict(row)
            for row in self._db.execute(
                "SELECT dataset, COUNT(*) AS active FROM latest GROUP BY dataset ORDER BY dataset"
            )
        ]
        last_run = dict(run) if run else None
        if last_run and isinstance(last_run.get("totals"), str):
            last_run["totals"] = json.loads(last_run["totals"])
        return {
            "last_run": last_run,
            "active_records": sum(row["active"] for row in datasets),
            "datasets": datasets,
        }


def connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


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
                "_first_seen": row["first_seen"],
                "_last_seen": row["last_seen"],
                "_last_changed": row["last_changed"],
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


def write_manifest(store: Store, path: Path, sources: Iterable[Source]) -> dict[str, Any]:
    """Write the dataset catalog consumed by the Bun dashboard."""
    counts = {
        row["dataset"]: (row["active"], row["last_changed"])
        for row in store._db.execute(
            "SELECT dataset, COUNT(*) AS active, MAX(last_changed) AS last_changed "
            "FROM latest GROUP BY dataset"
        )
    }
    run = store._db.execute(
        "SELECT id, started_at, finished_at, status, totals FROM runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    last_run = None
    if run is not None:
        last_run = dict(run)
        last_run["totals"] = json.loads(last_run["totals"]) if last_run["totals"] else {}
    datasets = []
    for source in sources:
        active, changed = counts.get(source.dataset, (0, None))
        datasets.append(
            {
                "dataset": source.dataset,
                "group": source.group,
                "label": source.label,
                "primary": source.primary,
                "dashboard": source.dashboard,
                "count": active,
                "last_changed": changed,
            }
        )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "last_run": last_run,
        "datasets": datasets,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
