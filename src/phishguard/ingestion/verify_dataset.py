"""Read-only file inventory; rejects symlinks and never extracts untrusted archives."""

import hashlib
from pathlib import Path


def inventory(root, hash_files=False):
    root = Path(root).resolve(strict=True)
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Dataset contains symlinks; review it before processing")
        if not path.is_file():
            continue
        stat = path.stat()
        record = {"path": str(path.relative_to(root)), "bytes": stat.st_size}
        if hash_files:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            record["sha256"] = digest.hexdigest()
        yield record
