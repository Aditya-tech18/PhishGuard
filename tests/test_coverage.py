"""Regression: a normal login-shaped URL must not be presented as a verified threat."""

from phishguard.ml.model_registry import URLModel


def test_path_and_login_shape_expose_review_notice_without_altering_score(model_path):
    model = URLModel.load(model_path)
    login = model.predict("https://github.com/login")
    assert login["review_required"] is True
    assert "Legitimate login" in login["coverage_warning"]
    assert login["verdict"] in {"phishing", "low_risk"}
    assert 0 <= login["probability"] <= 1
    root = model.predict("https://github.com/")
    assert root["coverage_warning"] is None
    assert root["review_required"] is False
    assert model.predict("https://login.microsoftonline.com/")["review_required"] is True


def test_origin_only_artifact_ignores_path_without_skipping_validation(model_path):
    import hashlib
    import json
    import pytest

    document = json.loads(model_path.read_text())
    document["input_policy"] = "origin-only"
    if document["format"] == "phishguard-classifier-v2":
        canonical = {key: value for key, value in document.items() if key != "version"}
        document["version"] = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()[:16]
    model = URLModel(document)
    assert (
        model.predict("https://example.com/login?token=secret")["probability"]
        == model.predict("https://example.com/")["probability"]
    )
    assert model.predict("https://example.com/login")["review_required"] is True
    with pytest.raises(ValueError):
        model.predict("https://user:password@example.com/login")
