#!/usr/bin/env python3
"""Preview by default. Add missing code, back up replacements, never copy runtime data.

This is a merge helper, not an archive extractor. Run from an already extracted repository.
Refuses symlinks in both source and destination paths and never deletes target files.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
from datetime import datetime, timezone

ALLOWED_DIRS = {
    "src",
    "frontend",
    "extension",
    "tests",
    "docs",
    "scripts",
    "config",
    ".github",
    "deploy",
    ".streamlit",
}
ALLOWED_FILES = {
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "requirements.txt",
    "Makefile",
    ".gitignore",
    ".dockerignore",
    ".env.example",
    ".python-version",
    "MANIFEST.sha256",
    "BUILD_REPORT.md",
    "FILE_INDEX.md",
    "requirements-tested.txt",
    "install_to_mac.sh",
    "start_local.sh",
}
PROTECTED = {".env", ".git", ".venv", "data", "models", "reports", "logs", "backups"}


def digest(path):
    # Empty iCloud placeholders can block on open despite having no bytes to preserve.
    if path.stat().st_size == 0:
        return hashlib.sha256(b'').hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_chain(path):
    for parent in [path, *path.parents]:
        if parent.is_symlink():
            raise ValueError(f"Symlink path refused: {parent}")


def plan(source, target, replace=False):
    check_chain(source)
    check_chain(target)
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("Source and target must be separate trees")
    operations, conflicts = [], []
    for entry in sorted(source.rglob("*")):
        rel = entry.relative_to(source)
        if entry.is_symlink():
            raise ValueError(f"Source symlink refused: {rel}")
        if not entry.is_file() or "__pycache__" in rel.parts or entry.suffix == ".pyc":
            continue
        if rel.parts[0] in PROTECTED:
            continue
        if rel.parts[0] not in ALLOWED_DIRS and str(rel) not in ALLOWED_FILES:
            continue
        destination = target / rel
        check_chain(destination)
        if destination.exists() and not destination.is_file():
            raise ValueError(f"Expected regular file at {rel}")
        if not destination.exists():
            operations.append({"path": str(rel), "action": "add", "sha256": digest(entry)})
        elif digest(entry) != digest(destination):
            if destination.stat().st_size == 0 or replace:
                operations.append(
                    {
                        "path": str(rel),
                        "action": "replace",
                        "sha256": digest(entry),
                        "old_sha256": digest(destination),
                    }
                )
            else:
                conflicts.append(str(rel))
    return operations, conflicts


def apply(source, target, replace=False):
    operations, conflicts = plan(source, target, replace)
    if conflicts:
        raise ValueError("Conflicting nonempty code files; preview --replace-code and review first")
    # Backup is a sibling; never inside protected target data.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup = target.parent / (target.name + ".code-backup-" + stamp)
    check_chain(backup)
    backup.mkdir(mode=0o700, parents=False, exist_ok=False)
    journal = {"target": str(target), "operations": operations, "completed": []}
    journal_path = backup / "merge-journal.json"
    journal_path.write_text(json.dumps(journal, indent=2))
    target.mkdir(parents=True, exist_ok=True)
    for operation in operations:
        rel = Path(operation["path"])
        src, dst = source / rel, target / rel
        check_chain(dst)
        if digest(src) != operation["sha256"]:
            raise ValueError("Source changed after plan; merge stopped")
        if operation["action"] == "replace":
            if digest(dst) != operation["old_sha256"]:
                raise ValueError("Target changed after plan; merge stopped")
            saved = backup / "original" / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            if dst.stat().st_size == 0:
                saved.touch()
                saved.chmod(stat.S_IMODE(dst.stat().st_mode) & 0o755)
            else:
                shutil.copy2(dst, saved)
        elif dst.exists():
            raise ValueError("A new destination appeared; merge stopped")
        dst.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive new temporary file, then atomic replacement in same filesystem.
        temporary = dst.with_name(dst.name + ".phishguard-new")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as out, src.open("rb") as inp:
                shutil.copyfileobj(inp, out)
                out.flush()
                os.fsync(out.fileno())
            os.chmod(temporary, stat.S_IMODE(src.stat().st_mode) & 0o755)
            temporary.replace(dst)
        finally:
            if temporary.exists():
                temporary.unlink()
        journal["completed"].append(str(rel))
        journal_path.write_text(json.dumps(journal, indent=2))
    return {"merged": len(operations), "backup": str(backup), "journal": str(journal_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path.home() / "Desktop/PhishGuard")
    parser.add_argument("--source", type=Path, default=Path(__file__).absolute().parents[1])
    parser.add_argument("--apply", action="store_true", help="Without this flag, only preview")
    parser.add_argument(
        "--replace-code", action="store_true", help="Back up and replace conflicting code only"
    )
    args = parser.parse_args()
    source, target = args.source.absolute(), args.target.expanduser().absolute()
    if args.apply:
        result = apply(source, target, args.replace_code)
    else:
        operations, conflicts = plan(source, target, args.replace_code)
        result = {
            "mode": "preview",
            "operations": operations,
            "conflicts": conflicts,
            "protected": sorted(PROTECTED),
        }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
