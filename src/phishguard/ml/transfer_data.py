"""Private, deterministic screenshot derivatives and group-isolated transfer folds."""

import hashlib
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
from sklearn.model_selection import GroupShuffleSplit
from phishguard.common.files import atomic_json, reject_symlink_chain
from phishguard.ml.vision_dataset import read_manifest, summary
from phishguard.processing.process_images import validate_image


def prepare_transfer(root, manifest, directory, seed=2718, workers=4):
    """Exclude duplicate leakage symmetrically, then partition validation by group.

    Test pixels participate only in deterministic duplicate detection. No held-out labels
    are used to fit a transform/model or choose hyperparameters/thresholds.
    """
    from PIL import Image

    if type(workers) is not int or not 1 <= workers <= 8:
        raise ValueError("Derivative workers must be 1..8")
    directory = reject_symlink_chain(Path(directory).absolute())
    if directory.exists():
        raise ValueError("Choose a fresh private derivative directory")
    rows = read_manifest(root, manifest)
    directory.mkdir(parents=True, mode=0o700)
    images = directory / "images224"
    images.mkdir(mode=0o700)

    def derive(row):
        data = row["path"].read_bytes()
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("Source image changed after manifest validation")
        image = validate_image(data)
        fingerprint = hashlib.sha256(
            image.resize((128, 128), resample=Image.Resampling.BICUBIC).tobytes()
        ).hexdigest()
        destination = images / (row["sha256"] + ".png")
        image.resize((224, 224), resample=Image.Resampling.BILINEAR).save(destination, format="PNG")
        destination.chmod(0o600)
        return {
            **row,
            "path": str(row["path"]),
            "cache_path": str(destination),
            "pixel_hash": fingerprint,
        }

    groups = defaultdict(list)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(derive, rows):
            groups[row["pixel_hash"]].append(row)
    clean = []
    excluded = Counter()
    for duplicates in groups.values():
        if len({row["split"] for row in duplicates}) > 1:
            excluded["cross_split_pixel_duplicates"] += len(duplicates)
            continue
        if len({row["label"] for row in duplicates}) > 1:
            excluded["ambiguous_pixel_duplicates"] += len(duplicates)
            continue
        excluded["within_split_duplicates"] += len(duplicates) - 1
        clean.append(duplicates[0])
    validation = [row for row in clean if row["split"] == "val"]
    group_ids = np.array([row["group"] for row in validation])
    if len(set(group_ids)) < 4:
        raise ValueError("At least four validation groups required for separate calibration")
    _, calibration = next(
        GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=seed).split(
            np.zeros(len(validation)), groups=group_ids
        )
    )
    calibration_ids = {validation[index]["sha256"] for index in calibration}
    for row in clean:
        row["phase"] = (
            "calibration"
            if row["sha256"] in calibration_ids
            else "selection"
            if row["split"] == "val"
            else row["split"]
        )
    phases = ["train", "selection", "calibration"]
    if any(row["phase"] == "test" for row in clean):
        phases.append("test")
    domains = {phase: {row["group"] for row in clean if row["phase"] == phase} for phase in phases}
    for a, phase in enumerate(phases):
        if {row["label"] for row in clean if row["phase"] == phase} != {0, 1}:
            raise ValueError("Both classes must be represented in every transfer fold")
        if any(domains[phase] & domains[other] for other in phases[a + 1 :]):
            raise ValueError("Domain groups leak across transfer folds")
    report = {
        "source_summary": summary(rows),
        "clean_rows": len(clean),
        "excluded": dict(excluded),
        "counts": {
            phase: dict(
                Counter(
                    "phishing" if row["label"] else "legitimate"
                    for row in clean
                    if row["phase"] == phase
                )
            )
            for phase in phases
        },
        "selection_calibration_seed": seed,
        "group_overlap": False,
        "preprocessing": "RGB bilinear full-frame resize 224x224; ImageNet channel normalization",
        "limitations": "Input group/label provenance must be independently verified. Pixel deduplication does not remove every near-duplicate or source bias.",
    }
    atomic_json(directory / "records-private.json", {"records": clean})
    atomic_json(directory / "preparation.json", report)
    return clean, report
