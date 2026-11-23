"""Read leaderboard data out of the Next.js App Router flight payload.

The site renders the data server-side into inline scripts of the form
``self.__next_f.push([1, "..."])``. Parsel selects those script nodes; the
chunks are concatenated, then individual props are decoded on demand.
"""

from __future__ import annotations

import json
import re
from typing import Any

from parsel import Selector

PUSH = "self.__next_f.push("
ROW_SPLIT = re.compile(r"\n(?=[0-9a-z]+:)")
MISSING = object()


class ExtractionError(RuntimeError):
    pass


def script_payloads(html: str) -> list[str]:
    """Return the flight chunks carried by inline scripts, in page order."""
    chunks: list[str] = []
    for text in Selector(text=html).css("script::text").getall():
        start = text.find(PUSH)
        while start != -1:
            begin = start + len(PUSH) - 1
            raw = _balanced(text, begin, "(", ")")
            if raw:
                try:
                    chunk = json.loads(raw[1:-1])
                except json.JSONDecodeError:
                    chunk = None
                if isinstance(chunk, list) and len(chunk) > 1 and isinstance(chunk[1], str):
                    chunks.append(chunk[1])
            start = text.find(PUSH, start + 1)
    return chunks


def flight_payload(html: str) -> str:
    chunks = script_payloads(html)
    if not chunks:
        raise ExtractionError("no Next.js flight payload found (site layout changed?)")
    return "".join(chunks)


def _balanced(text: str, start: int, opener: str, closer: str) -> str | None:
    """Return text[start:]'s balanced opener/closer block, respecting strings."""
    depth = 0
    escaped = False
    in_string = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def json_props(payload: str, prop: str) -> list[Any]:
    """All decoded values of ``"prop": ...`` in the flight payload."""
    values: list[Any] = []
    needle = f'"{prop}":'
    offset = 0
    while (found := payload.find(needle, offset)) != -1:
        offset = found + len(needle)
        cursor = offset
        while cursor < len(payload) and payload[cursor].isspace():
            cursor += 1
        if cursor >= len(payload):
            continue
        opener = payload[cursor]
        closer = {"[": "]", "{": "}"}.get(opener)
        if closer is None:
            continue
        raw = _balanced(payload, cursor, opener, closer)
        if raw is None:
            continue
        try:
            values.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return values


def _is_record_list(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    records = [item for item in value if isinstance(item, dict)]
    references = [item for item in value if isinstance(item, str) and item.startswith("$")]
    # The flight encoder replaces repeated objects with "$row:path" refs.
    return bool(records) and len(records) + len(references) == len(value)


def array_props(payload: str, prop: str) -> list[list[dict[str, Any]]]:
    arrays = []
    for value in json_props(payload, prop):
        if not _is_record_list(value):
            continue
        arrays.append([item for item in value if isinstance(item, dict)])
    return arrays


def nested_value_tables(
    payload: str,
) -> list[tuple[int, int, list[dict[str, Any]]]]:
    """All arena tables, as ``(block, slice, records)``."""
    blocks: list[list[list[dict[str, Any]]]] = []
    for row in ROW_SPLIT.split(payload):
        if '"values"' not in row:
            continue
        _, _, body = row.partition(":")
        try:
            value = json.loads(body)
        except json.JSONDecodeError:
            continue
        found: list[list[dict[str, Any]]] = []
        _walk_values(value, found)
        if found:
            blocks.append(found)
    return [
        (block, index, records)
        for block, tables in enumerate(blocks)
        for index, records in enumerate(tables)
    ]


def nested_value_arrays(payload: str) -> list[list[dict[str, Any]]]:
    """Ranking tables encoded as nested ``[{formatted, values}]`` rows."""
    tables = [records for _, _, records in nested_value_tables(payload)]
    tables.sort(key=len, reverse=True)
    return tables


def _walk_values(value: Any, found: list[list[dict[str, Any]]]) -> None:
    if isinstance(value, list):
        if value and all(
            isinstance(item, dict)
            and isinstance(item.get("values"), dict)
            and isinstance(item["values"].get("elo"), (int, float))
            for item in value
        ):
            found.append([item["values"] for item in value])
            return
        for item in value:
            _walk_values(item, found)
    elif isinstance(value, dict):
        for item in value.values():
            _walk_values(item, found)


def dig(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return MISSING
        current = current[part]
    return current
