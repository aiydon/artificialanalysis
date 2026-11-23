from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .rsc import (
    MISSING,
    ExtractionError,
    array_props,
    dig,
    flight_payload,
    json_props,
    nested_value_arrays,
    nested_value_tables,
)
from .sources import Source

Row = tuple[str, dict[str, Any]]


def camel_to_kebab(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def record_key(record: dict[str, Any], source: Source, task: str | None = None) -> str:
    parts = []
    for path in source.key:
        value = dig(record, path)
        if value is not MISSING and value not in (None, ""):
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


def extract(html: str, source: Source) -> list[Row]:
    payload = flight_payload(html)
    rows: dict[str, dict[str, Any]] = {}

    if source.mode == "values":
        tables = nested_value_arrays(payload)
        if not tables:
            raise ExtractionError(f"{source.dataset}: no ranking table found")
        for record in tables[0]:
            rows[record_key(record, source)] = dict(record)

    elif source.mode == "tables":
        tables = nested_value_tables(payload)
        if not tables:
            raise ExtractionError(f"{source.dataset}: no ranking tables found")
        for block, index, records in tables:
            key = f"{block}:{index}"
            rows[key] = {
                "block": block,
                "slice": index,
                "model_count": len(records),
                "models": records,
            }

    elif source.mode == "path":
        values = json_props(payload, source.props[0])
        if not values or not isinstance(values[0], dict):
            raise ExtractionError(f"{source.dataset}: property {source.props[0]!r} not found")
        table = dig(values[0], source.unwrap or "")
        if not isinstance(table, list) or not table:
            raise ExtractionError(f"{source.dataset}: path {source.unwrap!r} is not an array")
        for raw in table:
            if not isinstance(raw, dict):
                raise ExtractionError(f"{source.dataset}: non-object record")
            rows[record_key(raw, source)] = dict(raw)

    else:
        for prop in source.props:
            tables = array_props(payload, prop)
            if not tables:
                raise ExtractionError(f"{source.dataset}: property {prop!r} not found")
            if source.choose == "largest":
                table = max(tables, key=len)
            elif source.choose == "last":
                table = tables[-1]
            else:
                table = tables[0]
            task = camel_to_kebab(prop) if source.task_field else None
            for raw in table:
                record = dict(raw)
                if task:
                    record["task"] = task
                rows[record_key(record, source, task)] = record

    if not rows:
        raise ExtractionError(f"{source.dataset}: no records extracted")
    return list(rows.items())
