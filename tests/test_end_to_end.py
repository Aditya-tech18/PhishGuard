from fastapi.testclient import TestClient
from phishguard.ml.train_models import train
from phishguard.api.main import create_app
from phishguard.common.config import Settings


def test_csv_training_api(demo_csv, tmp_path):
    model = tmp_path / "url-model.json"
    report = train(demo_csv, model, tmp_path / "evaluation.json")
    config = Settings("a" * 32, model, tmp_path / "events.db")
    with TestClient(create_app(config)) as client:
        response = client.post(
            "/api/v1/predict/url",
            headers={"X-API-Key": "a" * 32},
            json={"url": "https://example.com/about"},
        )
        assert response.status_code == 200
        assert response.json()["model_version"] == report["model_version"]
        assert 0 <= response.json()["probability"] <= 1
