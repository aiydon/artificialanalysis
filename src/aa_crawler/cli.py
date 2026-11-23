from __future__ import annotations

import json
from pathlib import Path

import click

from . import __version__
from .config import Settings, settings_from_env
from .crawl import run_forever, run_once
from .sources import SOURCES, dataset_names
from .store import Store, export_latest, write_manifest


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="aa-crawler")
@click.option("--data-dir", type=click.Path(path_type=Path), help="data directory (default: data)")
@click.option("--proxy", help="HTTP(S) proxy; empty string disables AA_PROXY")
@click.option("--timeout", type=float, help="request timeout in seconds")
@click.option("--retries", type=int, help="retry attempts per request")
@click.option("--workers", type=int, help="parallel page downloads (default: 4)")
@click.pass_context
def cli(
    ctx: click.Context,
    data_dir: Path | None,
    proxy: str | None,
    timeout: float | None,
    retries: int | None,
    workers: int | None,
) -> None:
    """Crawl artificialanalysis.ai leaderboards into SQLite."""
    base = settings_from_env()
    ctx.obj = Settings(
        data_dir=data_dir or base.data_dir,
        proxy=base.proxy if proxy is None else (proxy or None),
        timeout=base.timeout if timeout is None else timeout,
        retries=base.retries if retries is None else retries,
        interval=base.interval,
        jitter=base.jitter,
        workers=base.workers if workers is None else workers,
    )
    if ctx.obj.workers < 1:
        raise click.BadParameter("must be at least 1", param_hint="--workers")


@cli.command()
@click.pass_obj
def once(settings: Settings) -> None:
    """Crawl every dataset once."""
    store = Store(settings.db_path)
    try:
        report = run_once(settings, store)
    finally:
        store.close()
    click.echo(report.summary_line())
    if report.errors:
        click.echo(report.error_line())
    if report.status == "failed":
        raise SystemExit(1)


@cli.command()
@click.option("--interval", type=float, help="seconds between crawls (default: 7200)")
@click.option("--jitter", type=float, help="random +/- fraction on the interval")
@click.pass_obj
def daemon(settings: Settings, interval: float | None, jitter: float | None) -> None:
    """Crawl forever, printing one summary line per run."""
    if interval is not None:
        if interval <= 0:
            raise click.BadParameter("must be positive", param_hint="--interval")
        settings = settings.model_copy(update={"interval": interval})
    if jitter is not None:
        settings = settings.model_copy(update={"jitter": jitter})

    store = Store(settings.db_path)
    try:
        run_forever(settings, store, echo=click.echo)
    finally:
        store.close()


@cli.command()
@click.pass_obj
def export(settings: Settings) -> None:
    """Export the latest snapshot without crawling."""
    store = Store(settings.db_path)
    try:
        written = export_latest(store, settings.export_dir, dataset_names())
        write_manifest(store, settings.data_dir / "datasets.json", SOURCES)
    finally:
        store.close()
    click.echo(json.dumps(written, indent=2))


@cli.command()
@click.pass_obj
def stats(settings: Settings) -> None:
    """Show the last run and active record counts."""
    store = Store(settings.db_path)
    try:
        click.echo(json.dumps(store.stats(), indent=2, ensure_ascii=False))
    finally:
        store.close()


@cli.command("datasets")
def list_datasets() -> None:
    """List datasets grouped by area."""
    grouped: dict[str, list] = {}
    for source in SOURCES:
        grouped.setdefault(source.group, []).append(source)
    for group, sources in grouped.items():
        click.echo(f"[{group}]")
        for source in sources:
            click.echo(f"  {source.dataset:<34} {source.label}")


@cli.command()
@click.argument("dataset")
@click.argument("key")
@click.option("--limit", default=20, show_default=True, help="number of changes to show")
@click.pass_obj
def history(settings: Settings, dataset: str, key: str, limit: int) -> None:
    """Show recorded changes for one dataset record."""
    store = Store(settings.db_path)
    try:
        rows = store.history(dataset, key, limit)
    finally:
        store.close()
    if not rows:
        raise click.ClickException(f"no changes for {dataset}/{key}")
    for row in rows:
        click.echo(f"{row['observed_at']}  {row['change']:<6}  {row['payload']}")


def main() -> None:
    cli(prog_name="aa-crawler")
