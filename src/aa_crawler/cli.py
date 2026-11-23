from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from dataclasses import replace

from . import __version__
from .config import Settings, settings_from_env
from .crawl import print_stats, run_forever, run_once
from .sources import dataset_names
from .store import Store, export_latest

log = logging.getLogger(__name__)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-dir", help="directory for aa.db and exports (default: data)")
    parser.add_argument(
        "--proxy",
        help="HTTP(S) proxy, e.g. http://127.0.0.1:7890; empty string disables it",
    )
    parser.add_argument("--timeout", type=float, help="request timeout in seconds")
    parser.add_argument("--retries", type=int, help="retry attempts per request")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aa-crawler",
        description="Crawl leaderboard datasets from artificialanalysis.ai into SQLite.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    once = sub.add_parser("once", help="crawl every dataset once")
    _add_common(once)

    daemon = sub.add_parser("daemon", help="crawl forever on a fixed interval")
    _add_common(daemon)
    daemon.add_argument("--interval", type=float, help="seconds between crawls")
    daemon.add_argument("--jitter", type=float, help="random +/- fraction on the interval")

    export = sub.add_parser("export", help="export the latest snapshot without crawling")
    _add_common(export)

    stats = sub.add_parser("stats", help="show the last run and latest record counts")
    _add_common(stats)

    sub.add_parser("datasets", help="list dataset names")
    return parser


def _settings(args: argparse.Namespace) -> Settings:
    settings = settings_from_env()
    overrides = {}
    if getattr(args, "data_dir", None):
        overrides["data_dir"] = type(settings.data_dir)(args.data_dir)
    if getattr(args, "proxy", None) is not None:
        overrides["proxy"] = args.proxy or None
    if getattr(args, "timeout", None) is not None:
        overrides["timeout"] = args.timeout
    if getattr(args, "retries", None) is not None:
        overrides["retries"] = args.retries
    if getattr(args, "interval", None) is not None:
        overrides["interval"] = args.interval
    if getattr(args, "jitter", None) is not None:
        overrides["jitter"] = args.jitter
    return replace(settings, **overrides)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = build_parser().parse_args(argv)

    if args.command == "datasets":
        print("\n".join(dataset_names()))
        return 0

    settings = _settings(args)
    if settings.interval <= 0:
        raise SystemExit("--interval must be positive")

    store = Store(settings.db_path)
    try:
        if args.command == "once":
            report = run_once(settings, store)
            print(report.summary())
            return 0 if report.status != "failed" else 1
        if args.command == "daemon":
            run_forever(settings, store)
            return 0
        if args.command == "export":
            written = export_latest(store, settings.export_dir, dataset_names())
            print(written)
            return 0
        if args.command == "stats":
            print_stats(store)
            return 0
    finally:
        store.close()
    return 0
