import json
from pathlib import Path
import pytest
from phishguard.ml.registry import LocalRegistry, QualityGate
from phishguard.ml.tournament import train_tournament
from phishguard.common.files import atomic_json, atomic_bytes, read_json, exclusive_lock
from phishguard.ml.offline_evaluation import evaluate_file


def test_register_gate_activate_and_detect_corruption(demo_csv, tmp_path):
    report = train_tournament(
        demo_csv, tmp_path / "trained", profile="fast", bootstrap_repetitions=0
    )
    model = tmp_path / "trained/url-model.json"
    evaluation = tmp_path / "trained/evaluation.json"
    registry = LocalRegistry(tmp_path / "registry")
    result = registry.register(model, evaluation)
    assert result["version"] == report["model_version"]
    assert registry.register(model, evaluation)["already_registered"] is True
    version = report["model_version"]
    registry.activate(version, QualityGate(min_test_rows=10))
    assert registry.active()["pointer"]["version"] == version
    assert registry.list()[0]["valid"] is True
    registered = Path(registry.active()["model_path"])
    registered.write_text(registered.read_text() + " ")
    with pytest.raises(ValueError, match="checksum"):
        registry.active()
    assert registry.list()[0]["valid"] is False


@pytest.mark.parametrize("version", ["../outside", "bad", "", "a" * 17, "A" * 16])
def test_registry_rejects_path_versions(tmp_path, version):
    with pytest.raises(ValueError):
        LocalRegistry(tmp_path).version_dir(version)


def test_quality_gate_is_explicit_and_fail_closed():
    assert not QualityGate().assess({})["accepted"]
    assert not QualityGate().assess({"test": {"precision": float("nan")}})["accepted"]
    with pytest.raises(ValueError):
        QualityGate(min_precision=2)


def test_atomic_artifact_no_clobber_and_finite_json(tmp_path):
    path = tmp_path / "state.json"
    atomic_json(path, {"hello": "world"})
    with pytest.raises(FileExistsError):
        atomic_bytes(path, b"new")
    assert read_json(path) == {"hello": "world"}
    with pytest.raises(ValueError):
        atomic_json(tmp_path / "bad.json", {"value": float("nan")})
    with exclusive_lock(tmp_path / "locks"):
        with pytest.raises(FileExistsError), exclusive_lock(tmp_path / "locks"):
            pass


def test_offline_evaluate_does_not_refit(demo_csv, tmp_path, model_path):
    original = model_path.read_bytes()
    report = evaluate_file(model_path, demo_csv, tmp_path / "evaluation.json", bootstrap=20)
    assert report["metrics"]["rows"] == 240
    assert model_path.read_bytes() == original
    assert "url" not in json.dumps(report)
