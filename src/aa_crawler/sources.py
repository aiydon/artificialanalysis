from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from .rsc import ExtractionError, array_prop, flight_payload


@dataclass(frozen=True)
class Source:
    """A leaderboard dataset embedded in one page's flight payload."""

    dataset: str
    path: str
    props: tuple[str, ...]
    key: tuple[str, ...]
    unwrap: str | None = None
    task_field: bool = False


SOURCES: tuple[Source, ...] = (
    # Model variants (e.g. "Nova 2.0 Omni (Medium)") share release.slug but
    # differ by suffix, so the suffix is part of the identity.
    Source(
        "llm_models",
        "/leaderboards/models",
        ("initialModels",),
        ("release.slug", "suffix"),
    ),
    Source(
        "llm_providers",
        "/leaderboards/providers",
        ("initialRows",),
        ("host.slug", "hostApiId", "model.release.slug", "label"),
    ),
    Source(
        "image_models",
        "/image/models",
        ("textToImage", "imageEditing"),
        ("slug",),
        task_field=True,
    ),
    Source(
        "video_models",
        "/video/models",
        (
            "textToVideo",
            "imageToVideo",
            "videoToVideo",
            "textToVideoAudio",
            "imageToVideoAudio",
            "videoToVideoAudio",
        ),
        ("slug",),
        task_field=True,
    ),
    # The page splits its 68 host models between hostModels (inline records)
    # and defaultSelected (records referenced by hostModels via "$row:path").
    Source("stt_models", "/speech-to-text", ("hostModels", "defaultSelected"), ("id",)),
    Source("tts_models", "/text-to-speech", ("hostModels",), ("slug",)),
    Source("music_models", "/music", ("initialData",), ("id",), unwrap="values"),
)

_MISSING = object()


def dataset_names() -> list[str]:
    return [source.dataset for source in SOURCES]


def camel_to_kebab(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def _dig(record: dict[str, Any], path: str) -> Any:
    value: Any = record
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value


def record_key(record: dict[str, Any], source: Source, task: str | None = None) -> str:
    parts = []
    for path in source.key:
        value = _dig(record, path)
        if value is not _MISSING and value not in (None, ""):
            parts.append(str(value))
    if not parts:
        for fallback in ("id", "slug", "name"):
            value = record.get(fallback)
            if value not in (None, ""):
                parts.append(str(value))
                break
    base = (
        "/".join(parts)
        or hashlib.sha1(json.dumps(record, sort_keys=True).encode()).hexdigest()[:16]
    )
    return f"{task}:{base}" if task else base


def extract(html: str, source: Source) -> list[tuple[str, dict[str, Any]]]:
    payload = flight_payload(html)
    rows: dict[str, dict[str, Any]] = {}

    for prop in source.props:
        records = array_prop(payload, prop)
        if records is None:
            raise ExtractionError(f"{source.dataset}: property {prop!r} not found")
        task = camel_to_kebab(prop) if source.task_field else None
        for raw in records:
            record = raw.get(source.unwrap) if source.unwrap else raw
            if not isinstance(record, dict):
                raise ExtractionError(f"{source.dataset}.{prop}: record is not an object")
            record = dict(record)
            if task:
                record["task"] = task
            rows[record_key(record, source, task)] = record

    if not rows:
        raise ExtractionError(f"{source.dataset}: no records extracted")
    return list(rows.items())
