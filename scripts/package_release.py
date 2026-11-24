#!/usr/bin/env python3
"""Package reviewed source files only, with a checksum manifest and ZIP verification.

Never includes raw data, model weights, local secrets, environments or generated caches.
The destination must be outside the source directory. This is a packaging tool, not an installer.
"""

import argparse
import hashlib
from pathlib import Path
import stat
import zipfile

OMIT_PARTS = {
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "data",
    "models",
    "reports",
    "logs",
    "backups",
    "build",
    "dist",
}


SOURCE_DIRS = {
    "src",
    "frontend",
    "tests",
    "scripts",
    "docs",
    "extension",
    "config",
    "deploy",
    ".github",
    ".streamlit",
}
SOURCE_ROOT_FILES = {
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
    "start_local.sh",
}
PRIVATE_SUFFIXES = {
    ".pyc",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".db-wal",
    ".db-shm",
    ".sqlite-wal",
    ".sqlite-shm",
    ".zip",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".keystore",
    ".pt",
    ".pth",
    ".onnx",
    ".pkl",
    ".pickle",
    ".joblib",
    ".safetensors",
    ".h5",
}


def source_files(root):
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(
            part in OMIT_PARTS or part.startswith(".venv") or part.endswith(".egg-info")
            for part in rel.parts
        ):
            continue
        if rel.parts[0] not in SOURCE_DIRS and str(rel) not in SOURCE_ROOT_FILES:
            continue
        if path.is_symlink():
            raise ValueError(f"Source symlink refused: {rel}")
        if not path.is_file() or path.suffix.lower() in PRIVATE_SUFFIXES:
            continue
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            continue
        if path.name == ".DS_Store" or path.name.startswith(".coverage"):
            continue
        yield path


def package(root, destination):
    root, destination = Path(root).resolve(strict=True), Path(destination).absolute()
    if root in destination.parents:
        raise ValueError("Write the release ZIP outside the source tree")
    if destination.exists():
        raise ValueError("Destination exists; choose a new release filename")
    files = [path for path in source_files(root) if path.name != "MANIFEST.sha256"]
    manifest = root / "MANIFEST.sha256"
    manifest.write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
            f"{path.relative_to(root).as_posix()}\n"
            for path in files
        )
    )
    files.append(manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        destination, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(files):
            name = root.name + "/" + path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 15, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            mode = 0o755 if path.suffix == ".sh" else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, path.read_bytes())
    with zipfile.ZipFile(destination) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"ZIP CRC error: {bad}")
        for path in files:
            name = root.name + "/" + path.relative_to(root).as_posix()
            if archive.read(name) != path.read_bytes():
                raise RuntimeError(f"ZIP source mismatch: {name}")
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix + ".sha256").write_text(
        f"{digest}  {destination.name}\n"
    )
    return {"files": len(files), "bytes": destination.stat().st_size, "sha256": digest}


if __name__ == "__main__":
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).absolute().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.source, args.output), indent=2))
