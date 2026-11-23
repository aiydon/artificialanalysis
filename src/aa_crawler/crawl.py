from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from .config import Settings
from .fetch import Fetcher
from .sources import SOURCES, dataset_names, extract
from .store import Store, export_latest

log = logging.getLogger(__name__)
FAILURE_RETRY_CAP = 300.0


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class RunReport:
    run_id: int
    status: str
    counts: dict[str, int]
    errors: dict[str, str]

    def summary(self) -> str:
        parts = [f"run #{self.run_id}: {self.status}"]
        parts += [f"{name}={count}" for name, count in self.counts.items()]
        if self.errors:
            parts.append(f"errors={list(self.errors)}")
        return ", ".join(parts)


def run_once(settings: Settings, store: Store) -> RunReport:
    started_at = utcnow()
    run_id = store.begin(started_at)
    counts: dict[str, int] = {}
    errors: dict[str, str] = {}

    try:
        with Fetcher(settings.proxy, settings.timeout, settings.retries) as fetcher:
            for source in SOURCES:
                try:
                    html = fetcher.get(source.path)
                    rows = extract(html, source)
                    store.add_dataset(run_id, source.dataset, rows, started_at)
                    counts[source.dataset] = len(rows)
                    log.info("%-14s %4d records", source.dataset, len(rows))
                except Exception as exc:
                    errors[source.dataset] = f"{type(exc).__name__}: {exc}"
                    store.fail_dataset(run_id, source.dataset, errors[source.dataset])
                    log.error("%-14s failed: %s", source.dataset, exc)

        if not counts:
            status = "failed"
        elif errors:
            status = "partial"
        else:
            status = "ok"
        store.finish(
            run_id,
            utcnow(),
            status,
            {"counts": counts, "errors": errors},
        )

        if counts:
            written = export_latest(store, settings.export_dir, counts)
            log.info("exported %s to %s", written, settings.export_dir)
    except Exception as exc:
        store.finish(run_id, utcnow(), "failed", {"counts": counts, "errors": {"crawl": str(exc)}})
        raise

    return RunReport(run_id, status, counts, errors)


def _next_delay(settings: Settings, failures: int) -> float:
    if failures == 0:
        base = settings.interval
    else:
        base = min(settings.interval, FAILURE_RETRY_CAP * 2 ** (failures - 1))
    delay = base * (1 + random.uniform(-settings.jitter, settings.jitter))
    return max(1.0, delay)


def run_forever(settings: Settings, store: Store) -> None:
    failures = 0
    log.info(
        "daemon started: interval=%.0fs datasets=%s",
        settings.interval,
        ",".join(dataset_names()),
    )
    while True:
        try:
            report = run_once(settings, store)
            failures = 0 if report.status != "failed" else failures + 1
            log.info(report.summary())
        except Exception:
            failures += 1
            log.exception("crawl run crashed")

        delay = _next_delay(settings, failures)
        log.info("next crawl at %s (in %.0fs)", utcnow(), delay)
        try:
            time.sleep(delay)
        except KeyboardInterrupt:
            log.info("daemon stopped")
            return


def print_stats(store: Store) -> None:
    print(json.dumps(store.stats(), indent=2))
