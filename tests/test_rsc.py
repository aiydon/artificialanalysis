import json

import pytest

from aa_crawler.rsc import ExtractionError, array_prop, flight_payload


def html_with(chunks: list[str]) -> str:
    scripts = [f"<script>self.__next_f.push([1,{json.dumps(chunk)}])</script>" for chunk in chunks]
    return "<html><body>" + "".join(scripts) + "</body></html>"


def test_chunks_are_reassembled_across_script_tags():
    html = html_with(['1:{"name":"a"}\n2:', '["x"]\n'])
    assert flight_payload(html) == '1:{"name":"a"}\n2:["x"]\n'


def test_array_prop_skips_decoys_and_handles_brackets_in_strings():
    payload = (
        '0:["chunkid","js"]\n'
        '1:{"initialModels":[],"note":"not an array of objects"}\n'
        '2:{"initialModels":[{"name":"a ] \\"quoted\\" [ b"},{"name":"c"}]}\n'
    )
    records = array_prop(payload, "initialModels")
    assert records is not None
    assert [record["name"] for record in records] == ['a ] "quoted" [ b', "c"]


def test_array_prop_missing_returns_none():
    assert array_prop('1:{"other":[{"a":1}]}', "initialModels") is None


def test_array_prop_keeps_inline_records_and_skips_flight_references():
    payload = (
        '1:{"hostModels":[{"id":"a"},"$3a:props:children:props:defaultSelected:0",{"id":"b"}]}'
    )
    records = array_prop(payload, "hostModels")
    assert [record["id"] for record in records] == ["a", "b"]


def test_array_prop_rejects_plain_strings():
    assert array_prop('1:{"hostModels":["a","b"]}', "hostModels") is None


def test_missing_payload_raises():
    with pytest.raises(ExtractionError):
        flight_payload("<html>nothing here</html>")
