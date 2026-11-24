import pytest
from phishguard.showcase import ShowcaseConfig, preflight


def test_preflight_uses_real_artifact_without_training(model_path, tmp_path):
    pytest.importorskip("streamlit")
    before = model_path.read_bytes()
    report = preflight(ShowcaseConfig(model_path, runtime_root=tmp_path), check_ports=False)
    assert report["local_inference"] == "passed"
    assert report["storage_enabled"] is False
    assert report["vision_enabled"] is False
    assert model_path.read_bytes() == before
    assert not list(tmp_path.glob("*/session-api-key.txt"))


@pytest.mark.parametrize(
    "kwargs",
    [dict(api_port=80), dict(api_port=8501), dict(run_seconds=-1), dict(startup_timeout=0)],
)
def test_invalid_showcase_configuration_is_rejected(model_path, kwargs):
    with pytest.raises(ValueError):
        ShowcaseConfig(model_path, **kwargs)


def test_startup_diagnostic_failure_cannot_leave_a_session_key(model_path, tmp_path, monkeypatch):
    import phishguard.showcase as stack

    monkeypatch.setattr(stack, "preflight", lambda config: {"model_version": "test"})

    def full_disk(*args, **kwargs):
        raise OSError("simulated diagnostic storage failure")

    monkeypatch.setattr(stack, "atomic_json", full_disk)
    with pytest.raises(OSError):
        stack.run(stack.ShowcaseConfig(model_path, runtime_root=tmp_path))
    assert not list(tmp_path.glob("*/session-api-key.txt"))
