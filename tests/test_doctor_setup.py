import importlib.util
import os
from pathlib import Path
import subprocess


def doctor():
    path = Path(__file__).parents[1] / "scripts/doctor.py"
    spec = importlib.util.spec_from_file_location("doctor_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_read_only_doctor_validates_artifact_and_hides_secrets(model_path, monkeypatch):
    tool = doctor()
    assert tool.check(model_path)["ready"] is True
    secret = "not-a-valid-secret"
    monkeypatch.setenv("PHISHGUARD_API_KEY", secret)
    result = tool.check(model_path, api_mode=True)
    assert result["ready"] is False
    assert secret not in str(result)


def test_setup_preserves_an_unmanaged_environment(tmp_path):
    path = Path(__file__).parents[1] / "scripts/setup_mac.sh"
    existing = tmp_path / "old-environment"
    existing.mkdir()
    (existing / "important.txt").write_text("old work")
    result = subprocess.run(
        ["bash", str(path)],
        env={**os.environ, "PHISHGUARD_VENV": str(existing)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "preserved" in result.stderr
    assert (existing / "important.txt").read_text() == "old work"
    assert sorted(item.name for item in existing.iterdir()) == ["important.txt"]
