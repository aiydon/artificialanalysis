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
    source = Source("image_models", "/image/models", ("textToImage",), ("slug",), task_field=True)
    payload = page(
        [
            '1:{"textToImage":[{"slug":"a","elo":1},{"slug":"b","elo":2}]}',
        ]
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


def test_record_key_falls_back_to_id():
    encoder = _src("test", "other", "Test", "/test", ("rows",), key=("host.slug",))
    assert record_key({"id": "abc", "host": {}}, encoder) == "abc"
    assert record_key({"id": "abc", "host": {"slug": "openai"}}, encoder) == "openai"
