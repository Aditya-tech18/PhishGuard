import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location(
    "safe_merge", Path(__file__).parents[1] / "scripts/safe_merge.py"
)
merge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge)


def test_preserve_runtime_and_backup(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    for root in (source, target):
        (root / "src").mkdir(parents=True)
        (root / "data/raw").mkdir(parents=True)
    (source / "src/main.py").write_text("new code")
    (target / "src/main.py").write_text("old code")
    (source / "data/raw/data.csv").write_text("must never copy")
    (target / "data/raw/data.csv").write_text("important dataset")
    (target / ".env").write_text("secret")
    (source / ".env").write_text("wrong")
    operations, conflicts = merge.plan(source, target)
    assert operations == [] and conflicts == ["src/main.py"]
    assert (target / "src/main.py").read_text() == "old code"
    with pytest.raises(ValueError):
        merge.apply(source, target)
    result = merge.apply(source, target, replace=True)
    assert (target / "src/main.py").read_text() == "new code"
    assert (target / "data/raw/data.csv").read_text() == "important dataset"
    assert (target / ".env").read_text() == "secret"
    assert (Path(result["backup"]) / "original/src/main.py").read_text() == "old code"
    assert merge.plan(source, target) == ([], [])


def test_symlink_escape_refused(tmp_path):
    source, target, outside = (tmp_path / name for name in ("source", "target", "outside"))
    (source / "src").mkdir(parents=True)
    target.mkdir()
    outside.mkdir()
    (source / "src/main.py").write_text("code")
    (target / "src").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        merge.plan(source, target)
    assert list(outside.iterdir()) == []
