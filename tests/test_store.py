import csv
import json
import sqlite3

from aa_crawler.store import Store, export_latest, flatten


def test_flatten_nested_and_lists():
    assert flatten({"a": {"b": 1}, "c": [1, 2], "d": None}) == {
        "a.b": 1,
        "c": "[1, 2]",
        "d": None,
    }


def test_incremental_insert_update_remove(tmp_path):
    store = Store(tmp_path / "aa.db")
    run1 = store.begin("2026-01-01T00:00:00+00:00")
    first = store.apply_dataset(
        run1, "models", [("m1", {"name": "old", "score": 1}), ("m2", {"score": 2})], "t1"
    )
    assert (first.inserted, first.updated, first.removed) == (2, 0, 0)

    run2 = store.begin("2026-01-02T00:00:00+00:00")
    second = store.apply_dataset(
        run2, "models", [("m1", {"name": "old", "score": 1}), ("m2", {"score": 3})], "t2"
    )
    assert (second.inserted, second.updated, second.unchanged, second.removed) == (0, 1, 1, 0)

    run3 = store.begin("2026-01-03T00:00:00+00:00")
    third = store.apply_dataset(run3, "models", [("m1", {"name": "old", "score": 1})], "t3")
    assert (third.inserted, third.updated, third.removed) == (0, 0, 1)

    latest = store.latest("models")
    assert [row["record_key"] for row in latest] == ["m1"]

    history = store.history("models", "m2", limit=10)
    assert [row["change"] for row in reversed(history)] == ["insert", "update", "remove"]
    removed = json.loads(history[0]["payload"])
    assert removed["score"] == 3

    store.close()


def test_export_latest_and_meta(tmp_path):
    store = Store(tmp_path / "aa.db")
    run = store.begin("t0")
    store.apply_dataset(run, "models", [("m1", {"name": "new", "score": 2})], "t1")
    written = export_latest(store, tmp_path / "export", ["models", "missing"])
    assert written == {"models": 1}

    rows = list(csv.DictReader((tmp_path / "export" / "models.csv").open()))
    assert rows[0]["name"] == "new"
    assert rows[0]["_key"] == "m1"
    assert rows[0]["_last_changed"] == "t1"

    record = json.loads((tmp_path / "export" / "models.jsonl").read_text().strip())
    assert record["_dataset"] == "models"
    assert record["score"] == 2
    store.close()
