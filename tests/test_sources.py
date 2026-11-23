import json

from aa_crawler.extract import camel_to_kebab, extract, record_key
from aa_crawler.sources import _src


def page(chunks: list[str]) -> str:
    return "".join(
        f"<script>self.__next_f.push([1,{json.dumps(chunk)}])</script>" for chunk in chunks
    )


def test_camel_to_kebab():
    assert camel_to_kebab("textToImage") == "text-to-image"
    assert camel_to_kebab("imageToVideoAudio") == "image-to-video-audio"


def test_extract_tags_task_and_uses_slug():
    encoder = _src(
        "test", "other", "Test", "/test", ("textToImage",), key=("slug",), task_field=True
    )
    rows = dict(
        extract(page(['1:{"textToImage":[{"slug":"a","elo":1},{"slug":"b","elo":2}]}']), encoder)
    )
    assert set(rows) == {"text-to-image:a", "text-to-image:b"}
    assert rows["text-to-image:a"]["task"] == "text-to-image"


def test_extract_merges_arrays_and_dedupes():
    encoder = _src(
        "stt",
        "speech",
        "Speech",
        "/stt",
        ("hostModels", "defaultSelected"),
        key=("id",),
    )
    rows = dict(
        extract(
            page(
                [
                    '1:{"hostModels":[{"id":"a"},{"id":"b"},"$3a:props:x"],'
                    '"defaultSelected":[{"id":"c"},{"id":"a"}]}'
                ]
            ),
            encoder,
        )
    )
    assert set(rows) == {"a", "b", "c"}


def test_extract_largest_array():
    encoder = _src(
        "chatbots", "agents", "Chatbots", "/x", ("chatbots",), key=("id",), choose="largest"
    )
    html = page(['1:{"chatbots":[{"id":"small"}],"chatbots":[{"id":"a"},{"id":"b"},{"id":"c"}]}'])
    assert set(dict(extract(html, encoder))) == {"a", "b", "c"}


def test_extract_values_mode():
    encoder = _src("music", "music", "Music", "/music", key=("id",), mode="values")
    html = page(
        [
            '1:{"title":"Arena"}\n2:[[null,[{"formatted":{"rank":1},"values":{"id":"a","elo":1200}}]]]\n'
        ]
    )
    rows = dict(extract(html, encoder))
    assert rows["a"]["elo"] == 1200


def test_extract_path_mode():
    encoder = _src(
        "changelog",
        "other",
        "Changelog",
        "/changelog",
        ("initialData",),
        mode="path",
        unwrap="data",
        key=("id",),
    )
    rows = dict(
        extract(page(['1:{"initialData":{"data":[{"id":"x","type":"modelAdded"}]}}']), encoder)
    )
    assert rows["x"]["type"] == "modelAdded"


def test_extract_tables_mode_keeps_each_slice():
    encoder = _src("slices", "image", "Slices", "/x", key=(), mode="tables")
    html = page(
        [
            '1:[[null,[{"values":{"id":"a","elo":1}},{"values":{"id":"b","elo":2}}],'
            '[{"values":{"id":"a","elo":3}}]]]\n'
        ]
    )
    rows = dict(extract(html, encoder))
    assert set(rows) == {"0:0", "0:1"}
    assert rows["0:0"]["model_count"] == 2
    assert rows["0:1"]["models"][0]["elo"] == 3


def test_record_key_falls_back_to_id():
    encoder = _src("test", "other", "Test", "/test", ("rows",), key=("host.slug",))
    assert record_key({"id": "abc", "host": {}}, encoder) == "abc"
    assert record_key({"id": "abc", "host": {"slug": "openai"}}, encoder) == "openai"
