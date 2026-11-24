import json
import numpy as np
import pytest
from phishguard.ml.model_registry import URLModel
from phishguard.ml.train_models import train, split_indices
from phishguard.ml.evaluate_models import evaluate


def test_portable_train_and_predict(demo_csv, tmp_path):
    output = tmp_path / "model.json"
    report = train(demo_csv, output, tmp_path / "report.json")
    assert report["unique_rows"] == 240
    model = URLModel.load(output)
    good = model.predict("https://ordinary.test/about")
    bad = model.predict("http://verify-123-account.test/login/secure/update?id=12")
    assert bad["probability"] > good["probability"]
    assert set(report["split_rows"]) == {"train", "validation", "test"}
    # This only validates mechanics on synthetic data; never asserts real-world accuracy.


def test_no_domain_leakage():
    groups = np.repeat([f"host{i}.test" for i in range(100)], 2)
    labels = np.tile([0, 1], 100)
    splits = split_indices(labels, groups)
    sets = [set(groups[s]) for s in splits]
    assert not sets[0] & sets[1]
    assert not sets[0] & sets[2]
    assert not sets[1] & sets[2]
    assert sum(map(len, splits)) == len(labels)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_hash", "wrong"),
        ("scale", [0] * 24),
        ("weights", [float("nan")] * 24),
        ("threshold", 2),
        ("bias", float("inf")),
    ],
)
def test_reject_invalid_artifact(model_path, field, value):
    doc = json.loads(model_path.read_text())
    doc[field] = value
    with pytest.raises(ValueError):
        URLModel(doc)


def test_metrics_ground_truth():
    report = evaluate([0, 0, 1, 1], [0.1, 0.8, 0.2, 0.9], 0.5)
    assert report["confusion"] == {"tn": 1, "fp": 1, "fn": 1, "tp": 1}
    assert report["false_positive_rate"] == 0.5
    assert report["f1"] == 0.5
    assert evaluate([0, 0], [0.1, 0.2])["roc_auc"] is None


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/?token=\nsecret",
        "https://example.com/?token=\tsecret",
        "https://example.com/?token=" + "a" * 2100,
    ],
)
def test_query_stripping_never_bypasses_original_validation(demo_csv, tmp_path, url):
    from phishguard.ml.tournament import train_tournament

    train_tournament(demo_csv, tmp_path / "run", profile="fast", bootstrap_repetitions=0)
    model = URLModel.load(tmp_path / "run/url-model.json")
    with pytest.raises(ValueError):
        model.predict(url)
