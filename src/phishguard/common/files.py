"""Atomic local artifact operations with explicit size/path bounds and no network I/O."""

from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def reject_symlink_chain(path):
    path = Path(path).absolute()
    for component in [path, *path.parents]:
        if component.is_symlink():
            raise ValueError("Symlink paths are not accepted for managed artifacts")
    return path


def sha256_file(path, max_bytes=None):
    path = Path(path)
    if max_bytes is not None and path.stat().st_size > max_bytes:
        raise ValueError("Artifact exceeds byte limit")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            if max_bytes is not None and size > max_bytes:
                raise ValueError("Artifact grew beyond byte limit")
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path, max_bytes=5_000_000):
    path = reject_symlink_chain(path)
    if not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError("Expected a bounded regular JSON file")
    with path.open("rb") as stream:
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("JSON file exceeds byte limit")

    def reject_constant(value):
        raise ValueError("Non-finite JSON constants are forbidden")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Non-finite JSON numbers are forbidden")
        return number

    return json.loads(data, parse_constant=reject_constant, parse_float=finite_float)


def atomic_bytes(path, data, *, replace=False, mode=0o600):
    path = reject_symlink_chain(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        raise FileExistsError("Refusing to overwrite an existing managed artifact")
    with NamedTemporaryFile(dir=path.parent, prefix=".artifact-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.chmod(temporary, mode)
        if replace:
            temporary.replace(path)
        else:
            # A hard link is an atomic no-clobber publication on the same filesystem.
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    # Best-effort directory sync makes a completed local rename durable across restart.
    try:
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass  # Some filesystems do not support directory fsync.
    return path


def atomic_json(path, document, *, replace=False):
    data = (json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    return atomic_bytes(path, data, replace=replace)


@contextmanager
def exclusive_lock(root):
    root = reject_symlink_chain(root)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".registry.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(str(os.getpid()))
            stream.flush()
            os.fsync(stream.fileno())
        yield
    finally:
        # Never guess that another process's stale lock can safely be removed.
        lock.unlink(missing_ok=True)
