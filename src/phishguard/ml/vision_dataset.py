"""Lazy image datasets and explicit site-isolated manifest validation.

The manifest stores relative local paths, labels, split and opaque group IDs. A caller must
supply meaningful site/campaign groups; the loader never fabricates them from image appearance.
Reports contain aggregate counts and fingerprints, not raw paths or group identifiers.
"""

import csv
import hashlib
from pathlib import Path
from collections import Counter
from phishguard.processing.process_images import validate_image

LABELS = {"legitimate": 0, "phishing": 1, "0": 0, "1": 1}
SPLITS = {"train", "val", "test"}


def safe_image_path(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("Image path must be a relative path without traversal")
    path = root / relative
    for part in [path, *path.parents]:
        if part == root.parent:
            break
        if part.is_symlink():
            raise ValueError("Image symlinks are forbidden")
    resolved = path.resolve(strict=True)
    if root not in resolved.parents or not resolved.is_file():
        raise ValueError("Image must be a regular file inside its declared root")
    if resolved.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("Only PNG/JPEG dataset files are supported")
    if not 0 < resolved.stat().st_size <= 5_000_000:
        raise ValueError("Invalid image byte size")
    return resolved


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest(root, manifest):
    root = Path(root).resolve(strict=True)
    records = []
    group_splits, image_splits = {}, {}
    seen_paths = set()
    with Path(manifest).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not {"path", "label", "split", "group"} <= set(reader.fieldnames or []):
            raise ValueError("Manifest needs path,label,split,group columns")
        for row in reader:
            if len(records) >= 500_000:
                raise ValueError("Image manifest exceeds supported row limit")
            split, group = row["split"], row["group"].strip()
            if split not in SPLITS or not group or len(group) > 256:
                raise ValueError("Invalid split or missing explicit site/campaign group")
            if row["label"] not in LABELS:
                raise ValueError("Unknown image label")
            path = safe_image_path(root, row["path"])
            if path in seen_paths:
                raise ValueError("Image path repeated in manifest")
            seen_paths.add(path)
            if group in group_splits and group_splits[group] != split:
                raise ValueError("Site/campaign group leaks across image splits")
            group_splits[group] = split
            digest = fingerprint(path)
            if digest in image_splits and image_splits[digest] != split:
                raise ValueError("Identical image bytes leak across image splits")
            image_splits[digest] = split
            records.append(
                {
                    "path": path,
                    "label": LABELS[row["label"]],
                    "split": split,
                    "group": group,
                    "sha256": digest,
                }
            )
    for split in {"train", "val"}:
        if {r["label"] for r in records if r["split"] == split} != {0, 1}:
            raise ValueError("Both classes are required in train and val image splits")
    return records


def folder_records(root):
    root = Path(root).resolve(strict=True)
    records, seen = [], {}
    for split in ["train", "val"]:
        for name in ["legitimate", "phishing"]:
            folder = root / split / name
            if not folder.is_dir() or folder.is_symlink():
                raise ValueError("Expected regular train/val class directories")
            count = 0
            for candidate in sorted(folder.rglob("*")):
                if candidate.is_symlink():
                    raise ValueError("Dataset symlinks are forbidden")
                if not candidate.is_file():
                    continue
                path = safe_image_path(root, candidate.relative_to(root))
                digest = fingerprint(path)
                if digest in seen and seen[digest] != split:
                    raise ValueError("Identical image leakage between train and val")
                seen[digest] = split
                records.append(
                    {"path": path, "label": LABELS[name], "split": split, "sha256": digest}
                )
                count += 1
            if not count:
                raise ValueError("Both image classes are required for each split")
    return records


class LazyImages:
    """Map-style Dataset protocol without importing torch until an item is loaded."""

    def __init__(self, records, split):
        self.records = [record for record in records if record["split"] == split]
        if not self.records:
            raise ValueError("Requested image split is empty")

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        import torch
        import numpy as np

        record = self.records[index]
        path = record["path"]
        if path.stat().st_size > 5_000_000:
            raise ValueError("Image grew beyond byte limit")
        image = validate_image(path.read_bytes()).resize((128, 128))
        array = np.asarray(image, dtype=np.float32).copy() / 255.0
        x = torch.from_numpy(array).permute(2, 0, 1)
        return x, torch.tensor([record["label"]], dtype=torch.float32)


def summary(records):
    counts = Counter((r["split"], r["label"]) for r in records)
    split_counts = {
        split: {"legitimate": counts[split, 0], "phishing": counts[split, 1]}
        for split in sorted({r["split"] for r in records})
    }
    payload = "\n".join(
        sorted(r["sha256"] + ":" + str(r["label"]) + ":" + r["split"] for r in records)
    )
    return {
        "split_counts": split_counts,
        "rows": len(records),
        "manifest_fingerprint": hashlib.sha256(payload.encode()).hexdigest(),
        "explicit_group_isolation": all("group" in r for r in records),
    }


def cache_records(records, directory):
    """Create lossless 128px RGB derivatives once; preserve original provenance hashes."""
    from phishguard.common.files import reject_symlink_chain, atomic_json

    directory = reject_symlink_chain(directory)
    if directory.exists():
        raise ValueError("Image cache must be a new directory")
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    cached = []
    for record in records:
        path = record["path"]
        if fingerprint(path) != record["sha256"]:
            raise ValueError("Raw image changed after manifest validation")
        image = validate_image(path.read_bytes()).resize((128, 128))
        destination = directory / (record["sha256"] + ".png")
        if not destination.exists():
            image.save(destination, format="PNG")
            destination.chmod(0o600)
        cached.append({**record, "path": destination})
    atomic_json(
        directory / "cache-summary.json",
        {
            "rows": len(cached),
            "image_size": [128, 128],
            "format": "lossless RGB PNG",
            "source_manifest": summary(records),
        },
    )
    return cached
