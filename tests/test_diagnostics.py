import numpy as np
import pytest
from phishguard.ml.diagnostics import calibration_bins, group_bootstrap, input_profile
from phishguard.analytics.drift import compare_profile
from phishguard.features.feature_schema import FEATURE_NAMES


def test_calibration_perfect_bins_and_empty_bins():
    report = calibration_bins([0, 1], [0.0, 1.0], bins=10)
    assert report["expected_calibration_error"] == 0
    assert report["bins"][0]["rows"] == 1
    assert report["bins"][9]["rows"] == 1
    assert report["bins"][1]["mean_probability"] is None


@pytest.mark.parametrize("probabilities", [[float("nan")], [-0.1], [1.1], []])
def test_invalid_calibration_is_rejected(probabilities):
    with pytest.raises(ValueError):
        calibration_bins([0], probabilities)


def test_group_bootstrap_is_reproducible_and_bounded():
    labels = np.tile([0, 1], 10)
    probabilities = np.tile([0.1, 0.9], 10)
    groups = np.repeat(np.arange(10), 2)
    first = group_bootstrap(labels, probabilities, groups, 0.5, repetitions=20, seed=7)
    second = group_bootstrap(labels, probabilities, groups, 0.5, repetitions=20, seed=7)
    assert first == second
    assert first["intervals"]["f1"]["lower"] == 1
    with pytest.raises(ValueError):
        group_bootstrap(labels, probabilities, groups, 0.5, repetitions=1)


def test_drift_flags_changes_without_claiming_accuracy():
    reference_x = np.zeros((20, len(FEATURE_NAMES)))
    profile = input_profile(reference_x)
    shifted = reference_x.copy()
    shifted[:, 0] = 5
    result = compare_profile(profile, shifted)
    assert result["flagged_features"] == ["url_length"]
    assert result["features"]["url_length"]["constant_reference_changed"] is True
    assert result["features"]["url_length"]["mean_shift_in_reference_std"] is None
    assert compare_profile(profile, reference_x)["flagged_features"] == []


def test_model_fingerprint_detects_numeric_tampering(demo_csv, tmp_path):
    import json
    from phishguard.ml.tournament import train_tournament
    from phishguard.ml.model_registry import URLModel

    train_tournament(demo_csv, tmp_path / "models", profile="fast", bootstrap_repetitions=0)
    path = tmp_path / "models/logistic_regression.json"
    document = json.loads(path.read_text())
    document["parameters"]["bias"] += 1
    with pytest.raises(ValueError, match="fingerprint"):
        URLModel(document)
