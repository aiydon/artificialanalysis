import csv
import json

from aa_crawler.store import Store, export_latest, flatten


def test_flatten_nested_and_lists():
    flat = flatten({"a": {"b": 1}, "c": [1, 2], "d": None})
    assert flat == {"a.b": 1, "c": "[1, 2]", "d": None}


def test_latest_uses_last_successful_run_and_export(tmp_path):
    store = Store(tmp_path / "aa.db")
    first = store.begin("2026-01-01T00:00:00+00:00")
    store.add_dataset(first, "models", [("m1", {"name": "old", "score": 1})], "t1")
    store.finish(first, "t1", "ok", {})

    second = store.begin("2026-01-02T00:00:00+00:00")
    store.add_dataset(second, "models", [("m1", {"name": "new", "score": 2})], "t2")
    store.fail_dataset(second, "other", "boom")
    store.finish(second, "t2", "partial", {})

    latest = store.latest("models")
    assert len(latest) == 1
    assert json.loads(latest[0]["payload"])["name"] == "new"

    written = export_latest(store, tmp_path / "export", ["models", "other"])
    assert written == {"models": 1}

    rows = list(csv.DictReader((tmp_path / "export" / "models.csv").open()))
    assert rows[0]["name"] == "new"
    assert rows[0]["_key"] == "m1"
    assert rows[0]["_observed_at"] == "t2"

    record = json.loads((tmp_path / "export" / "models.jsonl").read_text().strip())
    assert record["_dataset"] == "models"
    assert record["score"] == 2
    store.close()
