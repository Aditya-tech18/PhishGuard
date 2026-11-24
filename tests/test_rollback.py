import importlib.util
from pathlib import Path
import pytest


def load(name):
    path = Path(__file__).parents[1] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def merged(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    for root in [source, target]:
        (root / "src").mkdir(parents=True)
    (source / "src/changed.py").write_text("new")
    (source / "src/added.py").write_text("added")
    (target / "src/changed.py").write_text("original")
    (target / "data/raw").mkdir(parents=True)
    (target / "data/raw/important").write_text("keep")
    result = load("safe_merge").apply(source, target, replace=True)
    return target, Path(result["journal"])


def test_preview_then_restore_and_preserve_data(tmp_path):
    target, journal = merged(tmp_path)
    tool = load("rollback_merge")
    assert len(tool.rollback(journal)["operations"]) == 2
    assert (target / "src/changed.py").read_text() == "new"
    result = tool.rollback(journal, apply=True)
    assert len(result["completed"]) == 2
    assert (target / "src/changed.py").read_text() == "original"
    assert not (target / "src/added.py").exists()
    assert (target / "data/raw/important").read_text() == "keep"
    assert Path(result["snapshot"], "src/changed.py").read_text() == "new"


def test_later_user_edits_block_entire_rollback(tmp_path):
    target, journal = merged(tmp_path)
    (target / "src/changed.py").write_text("later work")
    with pytest.raises(ValueError, match="later user edits"):
        load("rollback_merge").rollback(journal, apply=True)
    assert (target / "src/changed.py").read_text() == "later work"
    assert (target / "src/added.py").exists()


@pytest.mark.parametrize(
    "path", ["../outside", "/tmp/outside", ".env", "data/raw/file", "models/trained/model"]
)
def test_untrusted_journal_paths_rejected(path):
    with pytest.raises(ValueError):
        load("rollback_merge").checked_relative(path)
