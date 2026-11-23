import json

import pytest

from aa_crawler.rsc import (
    ExtractionError,
    array_props,
    flight_payload,
    json_props,
    nested_value_arrays,
)


def page(chunks: list[str]) -> str:
    scripts = [f"<script>self.__next_f.push([1,{json.dumps(chunk)}])</script>" for chunk in chunks]
    return "<html><body>" + "".join(scripts) + "</body></html>"


def test_chunks_are_reassembled_across_script_tags():
    assert flight_payload(page(['1:{"name":"a"}\n2:', '["x"]\n'])) == '1:{"name":"a"}\n2:["x"]\n'


def test_array_props_skips_decoys_and_keeps_refs():
    payload = (
        '0:["chunkid","js"]\n'
        '1:{"initialModels":[],"note":"not a table"}\n'
        '2:{"initialModels":[{"name":"a ] \\"quoted\\" [ b"},"$3a:props:x",{"name":"c"}]}\n'
    )
    tables = array_props(payload, "initialModels")
    assert [[row["name"] for row in table] for table in tables] == [['a ] "quoted" [ b', "c"]]


def test_array_props_missing_returns_empty():
    assert array_props('1:{"other":[{"a":1}]}', "initialModels") == []


def test_json_props_reads_object():
    payload = '1:{"initialData":{"data":[{"id":"x"}]}}\n'
    assert json_props(payload, "initialData") == [{"data": [{"id": "x"}]}]


def test_nested_value_arrays_selects_arena_rows():
    payload = (
        '1:{"title":"AA-Image"}\n'
        '2:[[null,[{"formatted":{"rank":1},"values":{"id":"a","elo":1200}},'
        '{"formatted":{"rank":2},"values":{"id":"b","elo":1100}}]]]\n'
    )
    tables = nested_value_arrays(payload)
    assert len(tables) == 1
    assert [row["id"] for row in tables[0]] == ["a", "b"]


def test_nested_value_arrays_ignores_other_data():
    payload = '1:[{"id":"a","value":1},{"id":"b","value":2}]\n'
    assert nested_value_arrays(payload) == []


def test_missing_payload_raises():
    with pytest.raises(ExtractionError):
        flight_payload("<html>nothing here</html>")
