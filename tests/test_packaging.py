import importlib.util
from pathlib import Path
import zipfile
import pytest

spec = importlib.util.spec_from_file_location(
    "packager", Path(__file__).parents[1] / "scripts/package_release.py"
)
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


def test_release_excludes_secrets_and_runtime_data(tmp_path):
    root = tmp_path / "source"
    (root / "src").mkdir(parents=True)
    (root / "data/raw").mkdir(parents=True)
    (root / ".venv").mkdir()
    (root / "src/main.py").write_text('print("hello")\n')
    (root / ".env").write_text("SECRET=must-not-package")
    (root / ".env.example").write_text("EXAMPLE=placeholder")
    (root / "data/raw/data.csv").write_text("private dataset")
    (root / ".venv/local").write_text("environment")
    destination = tmp_path / "release.zip"
    result = packager.package(root, destination)
    assert result["files"] == 3  # source, example, checksum manifest
    with zipfile.ZipFile(destination) as archive:
        assert set(archive.namelist()) == {
            "source/src/main.py",
            "source/.env.example",
            "source/MANIFEST.sha256",
        }
        assert archive.testzip() is None
    assert destination.with_suffix(".zip.sha256").exists()
    with pytest.raises(ValueError, match="exists"):
        packager.package(root, destination)
    with pytest.raises(ValueError, match="outside"):
        packager.package(root, root / "bad.zip")


def test_runtime_reports_and_nested_private_material_never_enter_source_zip(tmp_path):
    root = tmp_path / "project"
    (root / "scripts").mkdir(parents=True)
    (root / "reports/local/session").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "src").mkdir()
    (root / "scripts/tool.py").write_text('print("ok")\n')
    (root / "reports/local/session/session-api-key.txt").write_text("private session key")
    (root / "config/private.pem").write_text("private certificate key")
    (root / "src/weights.pt").write_bytes(b"learned binary")
    (root / "personal-notes.txt").write_text("private user file")
    paths = {str(path.relative_to(root)) for path in packager.source_files(root)}
    assert paths == {"scripts/tool.py"}
