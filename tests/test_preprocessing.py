from collections import Counter
import pytest
from phishguard.ingestion.load_dataset import iter_records, DatasetError
from phishguard.processing.clean_urls import normalize_record


def test_csv_explicit_labels(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text(
        "address;target\nhttps://example.com;bad\nfile:///a;good\nhttps://test.com;unknown\n"
    )
    counts = Counter()
    records = list(iter_records(path, "address", "target", ";", {"bad": 1, "good": 0}, counts))
    assert records == [{"url": "https://example.com/", "label": 1}]
    assert counts == {"input": 3, "accepted": 1, "rejected": 2}
    with pytest.raises(DatasetError):
        list(iter_records(path))


def test_polarity_is_explicit():
    assert normalize_record("https://example.com", "legit", "phish", "legit")[1] == 0
    assert normalize_record("https://example.com", "phish", "phish", "legit")[1] == 1
    assert normalize_record("bad", "1")[2] == "invalid_url"
    with pytest.raises(ValueError):
        normalize_record("https://example.com", "a", "a", "a")


def test_conflicting_label_training(tmp_path):
    from phishguard.ml.train_models import train

    source = tmp_path / "bad.csv"
    source.write_text("url,label\nhttps://example.com/,1\nhttps://example.com/,0\n")
    with pytest.raises(ValueError, match="Conflicting"):
        train(source, tmp_path / "m.json", tmp_path / "r.json")
