"""Transparent post-first-test operating-policy revision; NOT a new independent test."""

from pathlib import Path
import hashlib
import json
import os

import numpy as np
import torch
from torch import nn
from torchvision.models import resnet18
from train_phish360 import Images, evaluate

ROOT = Path(os.environ.get("PHISH360_WORK_DIR", "reports/private-phish360"))


def main():
    torch.set_num_threads(4)
    original = json.loads((ROOT / "evaluation.json").read_text())
    fingerprint = hashlib.sha256((ROOT / "best.pt").read_bytes()).hexdigest()
    assert fingerprint == original["weights_sha256"]
    net = resnet18(weights=None)
    net.fc = nn.Sequential(
        nn.Dropout(0.3), nn.Linear(512, 128), nn.ReLU(), nn.Dropout(0.2), nn.Linear(128, 1)
    )
    net.load_state_dict(torch.load(ROOT / "best.pt", weights_only=True, map_location="cpu"))
    net.eval()
    records = json.loads((ROOT / "records-private.json").read_text())
    calibration = [r for r in records if r["phase"] == "calibration"]
    loader = torch.utils.data.DataLoader(Images(calibration), batch_size=16, num_workers=0)
    y, p = [], []
    with torch.inference_mode():
        for x, target in loader:
            p.extend(torch.sigmoid(net(x)).flatten().tolist())
            y.extend(target.int().tolist())
    y, p = np.asarray(y), np.asarray(p)
    candidates = []
    # Policy fixed before loading the saved test scores: emphasize recall while the
    # ordinary example-level Wilson lower precision bound on calibration stays >=85%.
    # This bound does not account for all template/domain dependence and is no live guarantee.
    for threshold in np.unique(p):
        if not 0 < float(threshold) < 1:
            continue
        prediction = p >= threshold
        tp = int(((y == 1) & prediction).sum())
        n = int(prediction.sum())
        if n < 100:
            continue
        phat = tp / n
        z = 1.959963984540054
        den = 1 + z * z / n
        lower = (
            phat + z * z / (2 * n) - z * np.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))
        ) / den
        if lower >= 0.85:
            candidates.append((tp / int((y == 1).sum()), phat, float(threshold)))
    if not candidates:
        raise RuntimeError("No calibration threshold meets the precision-bound constraint")
    recall, precision, threshold = max(candidates)
    calibration_metrics = evaluate(y, p, threshold)
    lock = {
        "weights_sha256": fingerprint,
        "threshold": threshold,
        "policy": "Maximum calibration recall subject to example-level Wilson 95% precision lower bound >=0.85 and >=100 predicted positives; ties prefer precision then threshold.",
        "calibration": calibration_metrics,
        "test_scores_not_loaded_during_threshold_selection": True,
        "first_test_result_previously_observed": True,
        "independent_test_claim": False,
        "reason": "Initial max-min calibration policy missed desired recall on the first official test. This is a transparent policy revision after that observation; do not treat the subsequent audit as fresh independent validation.",
    }
    (ROOT / "sensitivity-threshold-lock.json").write_text(json.dumps(lock, indent=2) + "\n")
    np.savez_compressed(ROOT / "calibration-predictions-private.npz", labels=y, scores=p)
    # Only now read the already observed frozen-model test scores for a regression audit.
    saved = np.load(ROOT / "test-predictions-private.npz", allow_pickle=False)
    audit = evaluate(saved["labels"], saved["scores"], threshold)
    report = {
        k: v
        for k, v in original.items()
        if k not in ("threshold", "calibration", "held_out_test", "target_met_on_test")
    }
    report.update(
        {
            "threshold": threshold,
            "calibration": calibration_metrics,
            "first_locked_test": original["held_out_test"],
            "first_locked_calibration": original["calibration"],
            "first_locked_target_met": original["target_met_on_test"],
            "operating_policy_revision": lock,
            "test_audit_after_policy_revision": audit,
            "target_met_on_test_audit": min(audit["precision"], audit["recall"]) >= 0.85,
            "new_independent_test_still_required": True,
        }
    )
    (ROOT / "sensitivity-evaluation.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {
                "threshold": threshold,
                "calibration": calibration_metrics,
                "previously_observed_test_audit": audit,
                "target_met_on_audit": report["target_met_on_test_audit"],
                "independent_test_claim": False,
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
