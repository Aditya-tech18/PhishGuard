import importlib.util
from pathlib import Path
import zipfile
import pytest
from phishguard.ml.tournament import train_tournament


def test_complete_bundle_is_runnable_without_raw_data(demo_csv, tmp_path, monkeypatch):
    scripts = Path(__file__).parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "complete_packager", scripts / "package_complete.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    models = tmp_path / "models"
    trained = train_tournament(demo_csv, models, profile="fast", bootstrap_repetitions=0)
    source = tmp_path / "source"
    (source / "src").mkdir(parents=True)
    (source / "src/main.py").write_text('print("ok")\n')
    (source / "reports/local").mkdir(parents=True)
    (source / "reports/local/key.txt").write_text("never package")
    output = tmp_path / "complete.zip"
    report = module.package(source, models, output)
    assert report["model_version"] == trained["model_version"]
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert "source/models/trained/url-model.json" in names
        assert "source/reports/evaluation.json" in names
        assert "source/BUNDLE_MANIFEST.sha256" in names
        assert not any("local/key.txt" in name for name in names)
        assert not any(name.endswith(".csv") for name in names)
    with pytest.raises(ValueError):
        module.package(source, models, output)
