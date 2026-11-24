from pathlib import Path
import pytest


def test_streamlit_consent_and_result(monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    import phishguard.dashboard.data_loader as loader

    calls = []

    def fake_api(method, path, payload=None):
        calls.append((method, path, payload))
        return {
            "probability": 0.2,
            "verdict": "low_risk",
            "model_version": "test-only",
            "disclaimer": "Model estimate only",
            "reasons": ["url_length"],
        }

    monkeypatch.setattr(loader, "api", fake_api)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "src/phishguard/dashboard/app.py"))
    app.run()
    assert not app.exception
    app.text_input[0].set_value("https://example.com/")
    app.button[0].click().run()
    assert not calls
    assert app.warning
    app.text_input[0].set_value("https://example.com/")
    app.checkbox[0].check()
    app.button[0].click().run()
    assert len(calls) == 1
    assert app.metric[0].value == "20.0%"
    assert not app.exception


def test_all_dashboard_views_have_consistent_reports(monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    import phishguard.dashboard.data_loader as loader
    import phishguard.dashboard.reports as reports

    def fake_api(method, path, payload=None):
        if path == "/health":
            return {"status": "ok", "model_version": "fixture", "vision_enabled": False}
        if path.endswith("/metrics"):
            return {
                "storage_enabled": False,
                "runtime": {"requests": 10, "latency_p95_ms": 2, "status_classes": {"2xx": 10}},
            }
        return {"storage_enabled": False, "items": []}

    def report(kind):
        if kind == "model":
            return {
                "winner": "random_forest",
                "test": {
                    "precision": 0.9,
                    "recall": 0.8,
                    "f1": 0.85,
                    "rows": 100,
                    "confusion": {"tp": 40, "tn": 40, "fp": 10, "fn": 10},
                },
            }
        if kind == "quality":
            return {
                "input": {"accepted": 100, "rejected": 2},
                "written": 100,
                "conflicting_unique_urls": 1,
            }
        return {"image_etl": {"files": 3, "valid_files": 3}}

    monkeypatch.setattr(loader, "api", fake_api)
    monkeypatch.setattr(reports, "local_report", report)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "src/phishguard/dashboard/app.py"))
    app.run()
    for view in ["Screenshot", "Overview", "Model report", "Data quality", "Retained metadata"]:
        app.radio[0].set_value(view).run()
        assert not app.exception, view
        assert not app.error, view
