"""Extract server-rendered data from the Next.js App Router payload.

artificialanalysis.ai ships its leaderboard records inside
``self.__next_f.push([1, "..."])`` flight chunks; the chunks concatenate to a
single payload of ``id:value`` rows. We only need the props that hold arrays of
records (e.g. ``initialModels``), so the parser locates the property and decodes
the balanced JSON array that follows it.
"""

from __future__ import annotations

import json
import re
from typing import Any

CHUNK_RE = re.compile(r"self\.__next_f\.push\((.*?)\)</script>", re.S)


class ExtractionError(RuntimeError):
    pass


def flight_payload(html: str) -> str:
    parts: list[str] = []
    for match in CHUNK_RE.finditer(html):
        try:
            chunk = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(chunk, list) and len(chunk) > 1 and isinstance(chunk[1], str):
            parts.append(chunk[1])
    if not parts:
        raise ExtractionError("no Next.js flight payload found (site layout changed?)")
    return "".join(parts)


def _balanced_array(text: str, start: int) -> str | None:
    """Return the JSON array starting at ``text[start]``, respecting strings."""
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
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def array_prop(payload: str, prop: str) -> list[dict[str, Any]] | None:
    """Find ``"prop": [ {...}, ... ]`` and return the first array of objects."""
    needle = f'"{prop}":'
    offset = 0
    while (found := payload.find(needle, offset)) != -1:
        offset = found + len(needle)
        cursor = offset
        while cursor < len(payload) and payload[cursor].isspace():
            cursor += 1
        if cursor >= len(payload) or payload[cursor] != "[":
            continue
        raw = _balanced_array(payload, cursor)
        if raw is None:
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, list) or not value:
            continue
        records = [item for item in value if isinstance(item, dict)]
        # The flight encoder replaces already-seen objects with "$row:path"
        # references; keep the inline objects, ignore the references.
        references = [item for item in value if isinstance(item, str) and item.startswith("$")]
        if records and len(records) + len(references) == len(value):
            return records
    return None
