import csv
from pathlib import Path
import pytest

pytestmark = pytest.mark.vision


def test_resized_duplicate_leakage_is_removed_before_calibration_split(tmp_path):
    pytest.importorskip("torch")
    from PIL import Image
    import numpy as np
    from phishguard.ml.transfer_data import prepare_transfer

    root = tmp_path / "images"
    root.mkdir()
    rows = []
    seed = 0
    for split, count in [("train", 40), ("val", 40), ("test", 20)]:
        for index in range(count):
            seed += 1
            array = np.random.default_rng(seed).integers(0, 255, (16, 16, 3), dtype=np.uint8)
            name = f"{split}-{index}.png"
            Image.fromarray(array).save(root / name)
            rows.append(
                {"path": name, "label": str(index % 2), "split": split, "group": f"opaque-{seed}"}
            )
    pixels = np.random.default_rng(9999).integers(0, 255, (16, 16, 3), dtype=np.uint8)
    for split, compression in [("train", 0), ("val", 9)]:
        name = f"duplicate-{split}.png"
        Image.fromarray(pixels).save(root / name, compress_level=compression)
        rows.append({"path": name, "label": "1", "split": split, "group": "duplicate-" + split})
    manifest = tmp_path / "manifest.csv"
    with manifest.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["path", "label", "split", "group"])
        writer.writeheader()
        writer.writerows(rows)
    records, report = prepare_transfer(root, manifest, tmp_path / "private-cache", workers=2)
    assert report["excluded"]["cross_split_pixel_duplicates"] == 2
    assert len(records) == 100
    phases = {
        phase: {r["group"] for r in records if r["phase"] == phase}
        for phase in ["train", "selection", "calibration", "test"]
    }
    assert not phases["selection"] & phases["calibration"]
    assert len(phases["selection"]) + len(phases["calibration"]) == 40
    assert not any("duplicate-" in r["path"] for r in records)
    assert report["group_overlap"] is False
    assert all(Path(r["cache_path"]).is_file() for r in records)


def test_calibration_threshold_and_uncertainty_are_explicit():
    pytest.importorskip("torch")
    from phishguard.ml.transfer_training import choose_balanced_threshold, intervals
    from phishguard.ml.evaluate_models import evaluate

    labels = [0, 0, 0, 1, 1, 1]
    scores = [0.1, 0.2, 0.6, 0.5, 0.8, 0.9]
    threshold = choose_balanced_threshold(labels, scores)
    result = evaluate(labels, scores, threshold)
    assert min(result["precision"], result["recall"]) >= 2 / 3
    bounds = intervals(result)
    assert bounds["precision"][0] < result["precision"] <= bounds["precision"][1]
    with pytest.raises(ValueError):
        choose_balanced_threshold([0, 0], [0.1, 0.2])
    with pytest.raises(ValueError):
        choose_balanced_threshold([0, 1], [0.2, float("nan")])


def test_atomic_torch_checkpoint_supports_hidden_temporary_names(tmp_path):
    torch = pytest.importorskip("torch")
    from phishguard.ml.transfer_training import _save_tensors

    path = tmp_path / "checkpoint.pt"
    _save_tensors(path, {"weights": torch.tensor([1.0, 2.0])})
    assert torch.equal(torch.load(path, weights_only=True)["weights"], torch.tensor([1.0, 2.0]))
    assert not list(tmp_path.glob(".transfer-*"))
