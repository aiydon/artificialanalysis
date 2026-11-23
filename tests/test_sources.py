import json

from aa_crawler.sources import Source, camel_to_kebab, extract, record_key


def page(chunks: list[str]) -> str:
    return "".join(
        f"<script>self.__next_f.push([1,{json.dumps(chunk)}])</script>" for chunk in chunks
    )


def test_camel_to_kebab():
    assert camel_to_kebab("textToImage") == "text-to-image"
    assert camel_to_kebab("imageToVideoAudio") == "image-to-video-audio"


def test_extract_tags_task_and_uses_slug():
    source = Source("image_models", "/image/models", ("textToImage",), ("slug",), task_field=True)
    payload = page(
        [
            '1:{"textToImage":[{"slug":"a","elo":1},{"slug":"b","elo":2}]}',
        ]
    )
    rows = dict(extract(payload, source))
    assert set(rows) == {"text-to-image:a", "text-to-image:b"}
    assert rows["text-to-image:a"]["task"] == "text-to-image"


def test_extract_unwraps_and_dedupes():
    source = Source("music_models", "/music", ("initialData",), ("id",), unwrap="values")
    payload = page(
        [
            '1:{"initialData":[{"values":{"id":"x","elo":1}},{"values":{"id":"x","elo":2}}]}',
        ]
    )
    rows = dict(extract(payload, source))
    assert list(rows) == ["x"]
    assert rows["x"]["elo"] == 2


def test_record_key_falls_back_to_id():
    source = Source("plain", "/x", ("rows",), ("host.slug",))
    assert record_key({"id": "abc", "host": {}}, source) == "abc"
    assert record_key({"id": "abc", "host": {"slug": "openai"}}, source) == "openai"
