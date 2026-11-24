import numpy as np
import pytest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from phishguard.ml.tournament import candidates, train_tournament
from phishguard.ml.model_registry import URLModel, export_classifier
from phishguard.ml.portable import Tree
from phishguard.features.url_features import vector
from phishguard.features.feature_schema import FEATURE_NAMES


@pytest.mark.parametrize("algorithm", sorted(candidates(profile="fast")))
def test_every_classifier_export_matches_sklearn(algorithm, tmp_path):
    urls = [f"https://site{i}.test/about" for i in range(40)] + [
        f"http://verify-{i}.test/login/secure?token={i}" for i in range(40)
    ]
    x = np.array([vector(url) for url in urls])
    labels = np.array([0] * 40 + [1] * 40)
    pipeline = Pipeline(
        [("scale", StandardScaler()), ("model", candidates(profile="fast")[algorithm])]
    )
    pipeline.fit(x, labels)
    output = tmp_path / (algorithm + ".json")
    export_classifier(pipeline, output, 0.5, {"test_only": True}, algorithm, query_policy="retain")
    model = URLModel.load(output)
    expected = pipeline.predict_proba(x)[:, 1]
    actual = [model.predict(url)["probability"] for url in urls]
    assert np.allclose(expected, actual, atol=1e-8, rtol=1e-7)
    assert model.algorithm == algorithm


def test_tournament_selects_without_domain_overlap(demo_csv, tmp_path):
    report = train_tournament(
        demo_csv, tmp_path / "tournament", profile="fast", bootstrap_repetitions=20
    )
    assert len(report["candidates"]) == 5
    assert report["winner"] in candidates(profile="fast")
    assert all(item["portable_parity"] for item in report["candidates"].values())
    assert len(set(report["split_fingerprints"].values())) == 3
    model = URLModel.load(tmp_path / "tournament/url-model.json")
    assert model.predict("https://example.com/?secret=a") == model.predict(
        "https://example.com/?secret=b"
    )
    assert report["uncertainty"]["repetitions"] == 20
    assert report["calibration"]["expected_calibration_error"] >= 0


def leaf():
    return {"left": [-1], "right": [-1], "features": [-2], "values": [0.25], "thresholds": [-2.0]}


@pytest.mark.parametrize(
    "field,value",
    [
        ("left", [0]),
        ("right", [99]),
        ("features", [100]),
        ("values", [float("nan")]),
        ("values", [2]),
        ("thresholds", [float("inf")]),
        ("left", [True]),
        ("left", []),
        ("values", [[0.25]]),
        ("features", [-1]),
    ],
)
def test_malformed_tree_rejected(field, value):
    document = leaf()
    document[field] = value
    with pytest.raises(ValueError):
        Tree(document)


def test_cycle_and_unreachable_tree_rejected():
    document = {
        "left": [1, 0, -1],
        "right": [2, 2, -1],
        "features": [0, 1, -2],
        "values": [0.5, 0.5, 0.2],
        "thresholds": [0.0, 0.0, -2.0],
    }
    with pytest.raises(ValueError, match="cycles"):
        Tree(document)
    document = leaf()
    for key in document:
        document[key] *= 2
    with pytest.raises(ValueError, match="Unreachable"):
        Tree(document)


def test_valid_tree_prediction():
    document = {
        "left": [1, -1, -1],
        "right": [2, -1, -1],
        "features": [0, -2, -2],
        "values": [0.5, 0.1, 0.9],
        "thresholds": [0.0, -2.0, -2.0],
    }
    tree = Tree(document)
    assert tree.predict(np.zeros(len(FEATURE_NAMES)))[0] == 0.1
    assert tree.predict(np.ones(len(FEATURE_NAMES)))[0] == 0.9
