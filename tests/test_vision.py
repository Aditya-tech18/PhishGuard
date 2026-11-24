import io
import pytest

pytestmark = pytest.mark.vision


def test_image_validation_and_cnn(tmp_path):
    pytest.importorskip("torch")
    from PIL import Image
    import torch
    from phishguard.ml.vision import architecture, VisionModel
    from phishguard.processing.process_images import validate_image

    stream = io.BytesIO()
    Image.new("RGB", (128, 128), "white").save(stream, format="PNG")
    image = stream.getvalue()
    assert validate_image(image).size == (128, 128)
    with pytest.raises(ValueError):
        validate_image(b"not an image")
    path = tmp_path / "weights.pt"
    torch.save(architecture().state_dict(), path)
    result = VisionModel(path).predict(image)
    assert 0 <= result["probability"] <= 1
    assert "Experimental" in result["disclaimer"]


def test_train_reload_and_opt_in_api(tmp_path, model_path):
    pytest.importorskip("torch")
    import numpy as np
    from PIL import Image
    from phishguard.ml.vision import train_vision, VisionModel
    from phishguard.api.main import create_app
    from phishguard.common.config import Settings
    from fastapi.testclient import TestClient
    import base64

    rng = np.random.default_rng(42)
    for split in ["train", "val"]:
        for label in ["legitimate", "phishing"]:
            folder = tmp_path / "images" / split / label
            folder.mkdir(parents=True)
            Image.fromarray(rng.integers(0, 255, (128, 128, 3), dtype=np.uint8)).save(
                folder / "one.png"
            )
    weights = tmp_path / "cnn.pt"
    report = train_vision(tmp_path / "images", weights, epochs=1)
    assert len(report["history"]) == 1
    data = (tmp_path / "images/train/legitimate/one.png").read_bytes()
    assert 0 <= VisionModel(weights).predict(data)["probability"] <= 1
    config = Settings(
        "a" * 32, model_path, tmp_path / "events.db", vision_path=weights, max_request_bytes=100000
    )
    with TestClient(create_app(config)) as client:
        assert client.get("/health").json()["vision_enabled"] is True
        assert client.get("/health").json()["vision_model_version"] == VisionModel(weights).version
        headers = {"X-API-Key": "a" * 32}
        encoded = base64.b64encode(data).decode()
        assert (
            client.post(
                "/api/v1/predict/image",
                headers=headers,
                json={"consent": False, "image_base64": encoded},
            ).status_code
            == 422
        )
        response = client.post(
            "/api/v1/predict/image",
            headers=headers,
            json={"consent": True, "image_base64": encoded},
        )
        assert response.status_code == 200
        assert response.json()["model_version"].startswith("experimental-cnn-v1-")
        assert (
            client.post(
                "/api/v1/predict/image",
                headers=headers,
                json={"consent": True, "image_base64": "!!!"},
            ).status_code
            == 422
        )
    assert not config.db_path.exists()


def test_vision_sidecar_rejects_wrong_identity_and_threshold(tmp_path):
    import json
    import hashlib

    torch = pytest.importorskip("torch")
    from phishguard.ml.vision import architecture, VisionModel

    weights = tmp_path / "vision.pt"
    torch.save(architecture().state_dict(), weights)
    digest = hashlib.sha256(weights.read_bytes()).hexdigest()
    sidecar = weights.with_suffix(".json")
    report = {
        "weights_sha256": "0" * 64,
        "model_version": "experimental-cnn-v1-" + digest[:12],
        "threshold": 0.64,
    }
    sidecar.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="identity"):
        VisionModel(weights)
    report["weights_sha256"] = digest
    report["threshold"] = float("nan")
    sidecar.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        VisionModel(weights)
    report["threshold"] = 0.64
    sidecar.write_text(json.dumps(report))
    assert VisionModel(weights).threshold == 0.64


def test_spatial_architecture_sidecar_load_and_invalid_architecture(tmp_path):
    import json
    import hashlib

    torch = pytest.importorskip("torch")
    from phishguard.ml.vision import architecture, VisionModel

    weights = tmp_path / "spatial.pt"
    torch.save(architecture("spatial-v2").state_dict(), weights)
    digest = hashlib.sha256(weights.read_bytes()).hexdigest()
    report = {
        "architecture": "spatial-v2",
        "model_version": "experimental-cnn-v1-" + digest[:12],
        "weights_sha256": digest,
        "threshold": 0.7,
    }
    weights.with_suffix(".json").write_text(json.dumps(report))
    model = VisionModel(weights)
    assert model.threshold == 0.7
    assert model.net(torch.zeros(1, 3, 128, 128)).shape == (1, 1)
    report["architecture"] = "arbitrary-unknown-architecture"
    weights.with_suffix(".json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="architecture"):
        VisionModel(weights)
