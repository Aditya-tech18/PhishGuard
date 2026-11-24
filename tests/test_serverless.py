"""Cloud-profile contract: the exported app uses the same authenticated portable model."""

import importlib.util
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from phishguard.api.serverless import create_cloud_app, cloud_hosts


def load_script(name):
    path = Path(__file__).parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cloud_bundle(tmp_path, model_path):
    root = Path(__file__).parents[1]
    from phishguard.ml.model_registry import URLModel

    model = URLModel.load(model_path)
    evaluation = tmp_path / "evaluation.json"
    evaluation.write_text(
        json.dumps(
            {
                "model_version": model.version,
                "test": {
                    "rows": 20,
                    "precision": 0.8,
                    "recall": 0.7,
                    "f1": 0.75,
                    "false_positive_rate": 0.1,
                },
            }
        )
    )
    output = tmp_path / "cloud"
    load_script("prepare_vercel").prepare(root, model_path, evaluation, output)
    return output


def test_exported_cloud_is_stateless_authenticated_and_host_restricted(cloud_bundle):
    env = {
        "PHISHGUARD_API_KEY": "z" * 40,
        "VERCEL_URL": "preview.vercel.app",
        "VERCEL_PROJECT_PRODUCTION_URL": "project.vercel.app",
    }
    app = create_cloud_app(cloud_bundle, env)
    with TestClient(app, base_url="https://project.vercel.app") as client:
        health = client.get("/health").json()
        assert health["vision_enabled"] is False
        assert client.get("/").status_code == 200
        assert "script-src 'self'" in client.get("/").headers["content-security-policy"]
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/assets/app.css").status_code == 200
        assert client.get("/api/v1/model-card").json()["rate_limit_scope"] == "per-warm-instance"
        assert (
            client.post("/api/v1/predict/url", json={"url": "https://example.com/"}).status_code
            == 401
        )
        headers = {"X-API-Key": "z" * 40}
        result = client.post(
            "/api/v1/predict/url", headers=headers, json={"url": "https://example.com/"}
        )
        assert result.status_code == 200
        assert 0 <= result.json()["probability"] <= 1
        assert (
            client.post(
                "/api/v1/predict/url", headers=headers, json={"url": "http://127.0.0.1/"}
            ).status_code
            == 422
        )
        assert client.get("/api/v1/predictions", headers=headers).json() == {
            "storage_enabled": False,
            "items": [],
        }
        assert (
            client.post(
                "/api/v1/predict/image",
                headers=headers,
                json={"consent": True, "image_base64": "eA=="},
            ).status_code
            == 503
        )
        assert client.get("/health", headers={"Host": "attacker.example"}).status_code == 400
    assert not list(cloud_bundle.rglob("*.db"))
    assert not list(cloud_bundle.rglob("*.pt"))
    assert not (cloud_bundle / "phishguard/ml/vision.py").exists()


@pytest.mark.parametrize(
    "value", ["*", "https://example.com", "example.com/path", "example..com", "example.com:443"]
)
def test_cloud_hosts_reject_ambiguous_configuration(value):
    with pytest.raises(ValueError):
        cloud_hosts({"PHISHGUARD_ALLOWED_HOSTS": value})


@pytest.mark.parametrize(
    "variable", ["PHISHGUARD_STORE_EVENTS", "PHISHGUARD_VISION_MODEL", "PHISHGUARD_REGISTRY"]
)
def test_cloud_rejects_unsupported_persistence_and_image_runtime(cloud_bundle, variable):
    with pytest.raises(ValueError):
        create_cloud_app(cloud_bundle, {"PHISHGUARD_API_KEY": "k" * 40, variable: "true"})


def test_cloud_fails_closed_without_key_and_on_model_card_mismatch(cloud_bundle):
    with pytest.raises(ValueError):
        create_cloud_app(cloud_bundle, {})
    card = cloud_bundle / "models/model-card.json"
    data = json.loads(card.read_text())
    data["model_version"] = "wrong"
    card.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="identity"):
        create_cloud_app(cloud_bundle, {"PHISHGUARD_API_KEY": "k" * 40})


def test_cloud_export_does_not_copy_raw_data_or_source_secret(cloud_bundle):
    assert set(p.name for p in cloud_bundle.iterdir()) == {
        "app.py",
        "vercel.json",
        "requirements.txt",
        ".python-version",
        "public",
        "phishguard",
        "models",
        "README.md",
        "LICENSE",
        ".gitignore",
        ".vercelignore",
    }
    assert not any(p.name in {"data", "reports", "tests", ".env"} for p in cloud_bundle.rglob("*"))


def test_cloud_extension_has_exact_one_origin_and_leaves_local_source_untouched(tmp_path):
    source = Path(__file__).parents[1] / "extension"
    old = (source / "background.js").read_bytes()
    result = load_script("configure_extension").configure(
        source, "https://my-phishguard.vercel.app", tmp_path / "cloud-extension"
    )
    assert result["host_permissions"] == ["https://my-phishguard.vercel.app/*"]
    assert (
        "https://my-phishguard.vercel.app"
        in (tmp_path / "cloud-extension/background.js").read_text()
    )
    assert (source / "background.js").read_bytes() == old


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.com",
        "https://example.com/path",
        "https://name:secret@example.com",
        "https://example.com?token=secret",
        "https://example.com#fragment",
        "https://*.vercel.app",
        "https://127.0.0.1",
    ],
)
def test_cloud_extension_rejects_unsafe_or_non_origin_configuration(origin, tmp_path):
    with pytest.raises(ValueError):
        load_script("configure_extension").configure(
            Path(__file__).parents[1] / "extension", origin, tmp_path / "out"
        )
