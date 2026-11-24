import importlib.util
import json
from pathlib import Path
import pytest
from phishguard.common.config import env_bool, read_yaml, Settings
from phishguard.common.logging import event
from phishguard.cli import main
from phishguard.analytics.generate_metrics import summarize
from phishguard.analytics.campaign_detection import candidate_campaigns


def test_curate_drops_all_ambiguous_without_touching_input(tmp_path):
    path = Path(__file__).parents[1] / "scripts/curate_dataset.py"
    spec = importlib.util.spec_from_file_location("curate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "source.csv"
    content = "url,label\nhttps://example.com,1\nhttps://example.com/,0\nhttps://other.com,0\n"
    source.write_text(content)
    with pytest.raises(ValueError, match="conflicting"):
        module.curate(source, tmp_path / "refused.csv")
    assert not (tmp_path / "refused.csv").exists()
    result = module.curate(source, tmp_path / "clean.csv", drop_conflicts=True)
    assert result["conflicting_unique_urls"] == 1
    assert result["written"] == 1
    assert source.read_text() == content
    assert "example.com" not in (tmp_path / "clean.csv").read_text()


def test_config_rejects_ambiguous_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("PHISHGUARD_STORE_EVENTS", "maybe")
    with pytest.raises(ValueError):
        env_bool("PHISHGUARD_STORE_EVENTS")
    yaml = tmp_path / "settings.yaml"
    yaml.write_text("version: 1\n")
    with pytest.raises(ValueError):
        read_yaml(yaml)
    yaml.write_text("version: 2\nprivacy:\n  telemetry: false\n")
    assert read_yaml(yaml)["privacy"]["telemetry"] is False
    with pytest.raises(ValueError):
        Settings("a" * 32, tmp_path / "model", tmp_path / "db", store_events=True)


def test_logs_drop_sensitive_fields(caplog):
    import logging

    with caplog.at_level(logging.INFO):
        event(
            logging.getLogger("test"), "prediction", count=1, url="secret-url", api_key="secret-key"
        )
    assert "secret" not in caplog.text
    assert "prediction" in caplog.text


def test_cli_inspection_and_prediction(demo_csv, model_path, capsys):
    main(["inspect", str(demo_csv)])
    result = json.loads(capsys.readouterr().out)
    assert result["counts"]["accepted"] == 240
    main(["predict", "https://example.com/", "--model", str(model_path)])
    assert json.loads(capsys.readouterr().out)["model_version"] == "test-only-zero-model"


def test_campaign_candidates_and_distribution_are_not_accuracy():
    urls = ["https://a.test/login/1", "https://b.test/login/2", "https://c.test/login/3"]
    candidates = candidate_campaigns(urls)
    assert candidates == [{"path_template": "/login/#", "distinct_hosts": 3, "status": "candidate"}]
    report = summarize([{"verdict": "phishing", "model_version": "v1"}])
    assert report["total"] == 1
    assert "not precision" in report["note"]
