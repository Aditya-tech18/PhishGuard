"""Prepare reproducible image splits without editing the source corpus.

Site groups may be explicitly derived from this corpus's documented numeric-id_hostname
filenames. The resulting grouping is a filename-derived proxy, not independently verified
capture provenance. Identical-content links join domain groups before split assignment.
"""

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import io
import re
from pathlib import Path
import numpy as np
from phishguard.common.files import atomic_bytes, atomic_json, reject_symlink_chain
from phishguard.features.url_features import domain_group, normalize_url
from phishguard.ml.train_models import split_indices
from phishguard.ml.vision_dataset import fingerprint, safe_image_path


class Components:
    def __init__(self):
        self.parents = {}

    def root(self, item):
        self.parents.setdefault(item, item)
        parent = item
        while self.parents[parent] != parent:
            parent = self.parents[parent]
        while self.parents[item] != item:
            following = self.parents[item]
            self.parents[item] = parent
            item = following
        return parent

    def join(self, first, second):
        a, b = self.root(first), self.root(second)
        if a != b:
            low, high = sorted([a, b])
            self.parents[high] = low


def filename_domain(path):
    match = re.fullmatch(r"\d+_([^_]+)(?:_.*)?", Path(path).stem)
    if match is None:
        raise ValueError("Expected numeric-id_hostname filename convention")
    host = match.group(1)
    normalized = normalize_url("https://" + host + "/")
    return domain_group(normalized)


def prepare(root, output, seed=42, filename_hosts=False, max_rows=100000):
    if not filename_hosts:
        raise ValueError(
            "Explicit filename-host derivation opt-in required; otherwise provide a trusted manifest"
        )
    root = reject_symlink_chain(root).resolve(strict=True)
    output = reject_symlink_chain(output)
    if output.exists() or root == output or root in output.parents:
        raise ValueError("Output must be a fresh directory outside the raw corpus")
    counts = Counter()
    candidates = []
    for label, directory in enumerate(["legitimate", "phishing"]):
        folder = root / directory
        if not folder.is_dir() or folder.is_symlink():
            raise ValueError("Explicit legitimate/phishing class folders required")
        for path in sorted(folder.rglob("*")):
            if path.is_symlink():
                raise ValueError("Source image symlink refused")
            if not path.is_file():
                continue
            counts["input_files"] += 1
            try:
                checked = safe_image_path(root, path.relative_to(root))
                group = filename_domain(checked)
            except (ValueError, OSError):
                counts["rejected_filename_or_file"] += 1
                continue
            candidates.append({"path": checked, "label": label, "domain": group})
            if len(candidates) > max_rows:
                raise ValueError("Image manifest row limit exceeded")

    def hashed(record):
        return {**record, "sha256": fingerprint(record["path"])}

    by_content = defaultdict(list)
    with ThreadPoolExecutor(max_workers=4) as executor:
        for record in executor.map(hashed, candidates):
            by_content[record["sha256"]].append(record)
    components = Components()
    unique = []
    for digest, records in sorted(by_content.items()):
        if len({record["label"] for record in records}) != 1:
            counts["ambiguous_content_groups"] += 1
            counts["ambiguous_content_images"] += len(records)
            continue
        first = records[0]
        for record in records:
            components.join(first["domain"], record["domain"])
        counts["duplicate_images_removed"] += len(records) - 1
        unique.append(first)
    if len(unique) < 30:
        raise ValueError("At least 30 unambiguous unique images required")
    labels = np.asarray([record["label"] for record in unique])
    groups = np.asarray([components.root(record["domain"]) for record in unique])
    splits = split_indices(labels, groups, seed)
    rows, sets = [], []
    distribution = {}
    for name, selected in zip(["train", "val", "test"], splits):
        chosen = [unique[index] for index in selected]
        group_set = {groups[index] for index in selected}
        sets.append(group_set)
        distribution[name] = {
            "rows": len(chosen),
            "groups": len(group_set),
            "legitimate": sum(record["label"] == 0 for record in chosen),
            "phishing": sum(record["label"] == 1 for record in chosen),
        }
        for index in selected:
            record = unique[index]
            rows.append(
                {
                    "path": record["path"].relative_to(root).as_posix(),
                    "label": record["label"],
                    "split": name,
                    "group": hashlib.sha256(groups[index].encode()).hexdigest(),
                }
            )
    if any(sets[a] & sets[b] for a, b in [(0, 1), (0, 2), (1, 2)]):
        raise RuntimeError("Connected-domain split leakage")
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=["path", "label", "split", "group"])
    writer.writeheader()
    writer.writerows(rows)
    atomic_bytes(output / "manifest.csv", buffer.getvalue().encode())
    report = {
        "seed": seed,
        "counts": dict(counts),
        "unique_rows": len(unique),
        "split_counts": distribution,
        "group_overlap": False,
        "content_overlap": False,
        "grouping": "registrable domain parsed from numeric-id_hostname filenames, unioned by identical content",
        "group_fingerprints": {
            name: hashlib.sha256("\n".join(sorted(values)).encode()).hexdigest()
            for name, values in zip(["train", "val", "test"], sets)
        },
        "limitations": "Filename-derived site grouping and publisher labels have not been independently verified; no temporal/source holdout.",
    }
    atomic_json(output / "preparation.json", report)
    return report
