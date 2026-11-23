from __future__ import annotations

import logging
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel
from tqdm import tqdm

from .config import Settings
from .extract import extract
from .fetch import Fetcher
from .sources import SOURCES, pages
from .store import Store, export_latest, write_manifest

log = logging.getLogger(__name__)
FAILURE_RETRY_CAP = 300.0


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RunReport(BaseModel):
    run_id: int
    status: str
    started_at: str
    finished_at: str
    duration: float
    pages: int
    datasets_total: int
    datasets_ok: int
    datasets_failed: int
    records: int
    inserted: int
    updated: int
    unchanged: int
    removed: int
    errors: dict[str, str]

    def summary_line(self, next_at: str | None = None) -> str:
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        parts = [
            stamp,
            self.status,
            f"{self.datasets_ok}/{self.datasets_total} datasets",
            f"{self.records:,} records",
            f"+{self.inserted:,} new",
            f"~{self.updated:,} changed",
            f"-{self.removed:,} removed",
            f"{self.duration:.1f}s",
        ]
        if next_at:
            parts.append(f"next {next_at}")
        return " | ".join(parts)

    def error_line(self) -> str:
        errors = [f"{name}: {message}" for name, message in self.errors.items()]
        return "  errors: " + "; ".join(errors)[:800]


def run_once(settings: Settings, store: Store) -> RunReport:
    started_at = utcnow()
    clock = time.monotonic()
    run_id = store.begin(started_at)
    grouped = pages()
    totals = {"records": 0, "inserted": 0, "updated": 0, "unchanged": 0, "removed": 0}
    errors: dict[str, str] = {}
    ok_datasets: list[str] = []

    progress = tqdm(
        total=len(grouped),
        desc="crawl",
        unit="page",
        leave=False,
        disable=None,
        file=sys.stderr,
    )
    try:
        with Fetcher(settings.proxy, settings.timeout, settings.retries) as fetcher:
            with ThreadPoolExecutor(max_workers=settings.workers) as pool:
                futures = {
                    pool.submit(fetcher.get, path): (path, sources)
                    for path, sources in grouped.items()
                }
                for future in as_completed(futures):
                    _, sources = futures[future]
                    progress.set_postfix_str(sources[0].group)
                    try:
                        html = future.result()
                    except Exception as exc:
                        message = f"{type(exc).__name__}: {exc}"
                        for source in sources:
                            store.fail_dataset(run_id, source.dataset, message)
                            errors[source.dataset] = message
                        progress.update(1)
                        continue

                    for source in sources:
                        try:
                            rows = extract(html, source)
                            stats = store.apply_dataset(
                                run_id, source.dataset, rows, observed_at=started_at
                            )
                            ok_datasets.append(source.dataset)
                            for field in totals:
                                totals[field] += getattr(stats, field)
                        except Exception as exc:
                            message = f"{type(exc).__name__}: {exc}"
                            store.fail_dataset(run_id, source.dataset, message)
                            errors[source.dataset] = message
                    progress.update(1)
    finally:
        progress.close()

    datasets_total = len(ok_datasets) + len(errors)
    if not ok_datasets:
        status = "failed"
    elif errors:
        status = "partial"
    else:
        status = "ok"

    finished_at = utcnow()
    report = RunReport(
        run_id=run_id,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        duration=time.monotonic() - clock,
        pages=len(grouped),
        datasets_total=datasets_total,
        datasets_ok=len(ok_datasets),
        datasets_failed=len(errors),
        errors=errors,
        **totals,
    )
    store.finish(
        run_id,
        finished_at,
        status,
        {"pages": len(grouped), "datasets_ok": len(ok_datasets), **totals, "errors": errors},
    )

    if ok_datasets:
        try:
            export_latest(store, settings.export_dir, ok_datasets)
            write_manifest(store, settings.data_dir / "datasets.json", SOURCES)
        except Exception:
            log.exception("export failed")

    return report


def _next_delay(settings: Settings, failures: int) -> float:
    if failures == 0:
        base = settings.interval
    else:
        base = min(settings.interval, FAILURE_RETRY_CAP * 2 ** (failures - 1))
    delay = base * (1 + random.uniform(-settings.jitter, settings.jitter))
    return max(1.0, delay)


def next_run_at(delay: float) -> str:
    target = datetime.now().astimezone() + timedelta(seconds=delay)
    return target.strftime("%Y-%m-%d %H:%M:%S")


def run_forever(settings: Settings, store: Store, echo: Callable[[str], Any] = print) -> None:
    failures = 0
    while True:
        try:
            report = run_once(settings, store)
            failures = 0 if report.status != "failed" else failures + 1
        except Exception as exc:
            failures += 1
            log.exception("crawl run crashed")
            echo(f"{datetime.now():%Y-%m-%d %H:%M:%S} | failed | {type(exc).__name__}: {exc}")
            report = None

        delay = _next_delay(settings, failures)
        next_at = next_run_at(delay)
        if report is not None:
            echo(report.summary_line(next_at))
            if report.errors:
                echo(report.error_line())

        try:
            time.sleep(delay)
        except KeyboardInterrupt:
            echo("daemon stopped")
            return
