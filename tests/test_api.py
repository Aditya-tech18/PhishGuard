from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from phishguard.api.main import create_app
from phishguard.common.config import Settings


def settings(model_path, tmp_path, **overrides):
    return Settings(
        api_key="k" * 32,
        model_path=model_path,
        db_path=tmp_path / "events.db",
        hmac_key="h" * 32,
        **overrides,
    )


def test_auth_prediction_privacy(model_path, tmp_path):
    app = create_app(settings(model_path, tmp_path, store_events=True))
    headers = {"X-API-Key": "k" * 32}
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert (
            client.post("/api/v1/predict/url", json={"url": "https://example.com"}).status_code
            == 401
        )
        response = client.post(
            "/api/v1/predict/url",
            headers=headers,
            json={"url": "https://example.com/?token=supersecret"},
        )
        assert response.status_code == 200
        assert "supersecret" not in response.text
        assert response.headers["cache-control"] == "no-store"
        listing = client.get("/api/v1/predictions", headers=headers).json()
        assert len(listing["items"]) == 1
        assert "url" not in listing["items"][0]
        assert client.get("/api/v1/metrics", headers=headers).json()["retained_predictions"] == 1
        assert client.delete("/api/v1/predictions", headers=headers).status_code == 200
        assert client.get("/api/v1/predictions", headers=headers).json()["items"] == []
    assert b"supersecret" not in (tmp_path / "events.db").read_bytes()


def test_input_limits_and_validation_redaction(model_path, tmp_path):
    with TestClient(create_app(settings(model_path, tmp_path))) as client:
        headers = {"X-API-Key": "k" * 32}
        bad = client.post(
            "/api/v1/predict/url",
            headers=headers,
            json={"url": "http://user:supersecret@example.com/"},
        )
        assert bad.status_code == 422
        assert "supersecret" not in bad.text
        assert (
            client.post("/api/v1/predict/url", headers=headers, content=b"x" * 65537).status_code
            == 413
        )
        assert (
            client.post(
                "/api/v1/predict/url",
                headers=headers,
                json={"url": "https://example.com", "extra": True},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/predict/batch",
                headers=headers,
                json={"items": [{"url": "https://example.com"}] * 33},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/predict/batch",
                headers=headers,
                json={"items": [{"url": "https://example.com"}]},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/predict/image",
                headers=headers,
                json={"consent": True, "image_base64": "AAAA"},
            ).status_code
            == 503
        )
        assert client.get("/health?secret=supersecret").status_code == 400


def test_rate_limit(model_path, tmp_path):
    with TestClient(create_app(settings(model_path, tmp_path, rate_limit=2))) as client:
        for _ in range(2):
            assert client.get("/api/v1/metrics").status_code == 401
        assert client.get("/api/v1/metrics").status_code == 429
        assert client.get("/health").status_code == 200


def test_no_storage_by_default(model_path, tmp_path):
    config = settings(model_path, tmp_path)
    with TestClient(create_app(config)) as client:
        response = client.post(
            "/api/v1/predict/url",
            headers={"X-API-Key": "k" * 32},
            json={"url": "https://example.com"},
        )
        assert response.status_code == 200
    assert not config.db_path.exists()


def test_fail_closed_model_and_secret(tmp_path):
    with pytest.raises(ValueError):
        Settings(api_key="short", model_path=Path("a"), db_path=Path("b"))
    app = create_app(settings(tmp_path / "missing", tmp_path))
    with pytest.raises(FileNotFoundError), TestClient(app):
        pass


def test_chunked_body_limit(model_path, tmp_path):
    with TestClient(create_app(settings(model_path, tmp_path))) as client:

        def chunks():
            for _ in range(70):
                yield b"x" * 1024

        response = client.post(
            "/api/v1/predict/url", headers={"X-API-Key": "k" * 32}, content=chunks()
        )
        assert response.status_code == 413
