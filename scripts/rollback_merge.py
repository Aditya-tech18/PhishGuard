#!/usr/bin/env python3
"""Preview-first rollback of one PhishGuard code merge, preserving later user edits.

Only files whose current digest equals the originally installed release digest are changed.
Any conflict stops the entire preflight. The source merge journal is data, never executable.
Protected runtime paths are rejected even if a journal is forged or accidentally edited.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile

PROTECTED = {".env", ".git", ".venv", "data", "models", "reports", "logs", "backups"}
ALLOWED = {
    "src",
    "tests",
    "scripts",
    "docs",
    "extension",
    "config",
    "deploy",
    ".github",
    ".streamlit",
}
ROOT_FILES = {
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "requirements.txt",
    "requirements-tested.txt",
    "Makefile",
    ".gitignore",
    ".dockerignore",
    ".env.example",
    ".python-version",
    "MANIFEST.sha256",
    "BUILD_REPORT.md",
    "FILE_INDEX.md",
    "install_to_mac.sh",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_path(path):
    for item in [path, *path.parents]:
        if item.is_symlink():
            raise ValueError("Symlink in rollback path")


def checked_relative(value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Invalid relative path in merge journal")
    if path.parts[0] in PROTECTED:
        raise ValueError("Journal attempts to change protected runtime data")
    if path.parts[0] not in ALLOWED and str(path) not in ROOT_FILES:
        raise ValueError("Journal path is outside the code allowlist")
    return path


def plan(journal_path):
    journal_path = Path(journal_path).absolute()
    check_path(journal_path)
    if journal_path.stat().st_size > 5_000_000:
        raise ValueError("Merge journal exceeds maximum size")
    journal = json.loads(journal_path.read_text())
    target = Path(journal["target"]).absolute()
    backup = journal_path.parent
    check_path(target)
    if target == backup or target in backup.parents or backup in target.parents:
        raise ValueError("Backup and target must be separate trees")
    operations = journal.get("operations", [])
    completed = set(journal.get("completed", []))
    if not isinstance(operations, list) or len(operations) > 10000:
        raise ValueError("Invalid merge journal operations")
    result, conflicts, seen = [], [], set()
    for operation in operations:
        relative = checked_relative(operation["path"])
        if str(relative) in seen:
            raise ValueError("Repeated journal path")
        seen.add(str(relative))
        if str(relative) not in completed:
            continue
        installed = target / relative
        check_path(installed)
        if not installed.is_file() or digest(installed) != operation["sha256"]:
            conflicts.append(str(relative))
            continue
        action = operation["action"]
        if action == "replace":
            original = backup / "original" / relative
            check_path(original)
            if not original.is_file() or digest(original) != operation["old_sha256"]:
                raise ValueError("Original backup is missing or its digest changed")
            result.append(
                {
                    "path": str(relative),
                    "action": "restore",
                    "current_sha256": operation["sha256"],
                    "original_sha256": operation["old_sha256"],
                }
            )
        elif action == "add":
            result.append(
                {
                    "path": str(relative),
                    "action": "remove_added_code",
                    "current_sha256": operation["sha256"],
                }
            )
        else:
            raise ValueError("Unknown journal action")
    return target, backup, result, conflicts


def rollback(journal_path, apply=False):
    target, backup, operations, conflicts = plan(journal_path)
    result = {
        "mode": "apply" if apply else "preview",
        "target": str(target),
        "operations": operations,
        "conflicts": conflicts,
    }
    if not apply:
        return result
    if conflicts:
        raise ValueError("Rollback refused: later user edits or missing files detected")
    # Keep the installed files too, so rollback itself remains reviewable/recoverable.
    saved = backup / "pre-rollback"
    if saved.exists():
        raise ValueError("This journal already has a rollback snapshot; review it manually")
    saved.mkdir(mode=0o700)
    for operation in operations:
        relative = Path(operation["path"])
        current = target / relative
        if digest(current) != operation["current_sha256"]:
            raise ValueError("Target changed during rollback; stop and review the journal")
        snapshot = saved / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current, snapshot)
    completed = []
    progress = backup / "rollback-journal.json"
    progress.write_text(json.dumps({"operations": operations, "completed": completed}, indent=2))
    for operation in operations:
        relative = Path(operation["path"])
        current = target / relative
        check_path(current)
        if digest(current) != operation["current_sha256"]:
            raise ValueError("Target changed during rollback; no later edits will be overwritten")
        if operation["action"] == "restore":
            original = backup / "original" / relative
            with NamedTemporaryFile(
                dir=current.parent, prefix=".rollback-", delete=False
            ) as stream:
                temporary = Path(stream.name)
                with original.open("rb") as source:
                    shutil.copyfileobj(source, stream)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                shutil.copymode(original, temporary)
                temporary.replace(current)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            # Deletion is explicit rollback of an unchanged file added by this merge only.
            current.unlink()
        completed.append(str(relative))
        progress.write_text(
            json.dumps({"operations": operations, "completed": completed}, indent=2)
        )
    return {**result, "completed": completed, "snapshot": str(saved)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(rollback(args.journal, args.apply), indent=2))


if __name__ == "__main__":
    main()
