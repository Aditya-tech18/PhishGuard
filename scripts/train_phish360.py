"""Image-only Phish360 experiment with locked selection/calibration/test stages."""

from pathlib import Path
import hashlib
import json
import math
import os
import time

import numpy as np
import torch
from torch import nn
from torchvision.models import resnet18
from torchvision.transforms import v2 as T
from PIL import Image
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score

ROOT = Path(os.environ.get("PHISH360_WORK_DIR", "reports/private-phish360"))
PRETRAINED = Path(
    os.environ.get("PHISH360_PRETRAINED", "models/private-initialization/resnet18-f37072fd.pth")
)
DEVICE = os.environ.get("PHISH360_DEVICE", "mps")


class Images(torch.utils.data.Dataset):
    def __init__(self, rows, augment=False):
        self.rows = rows
        ops = [T.ToImage(), T.ToDtype(torch.float32, scale=True)]
        if augment:
            ops += [
                T.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.05),
                T.RandomAffine(degrees=0, translate=(0.015, 0.015), scale=(0.97, 1.03), fill=1.0),
            ]
        self.transform = T.Compose(
            ops + [T.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225))]
        )

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        with Image.open(row["cache_path"]) as im:
            x = self.transform(im.convert("RGB"))
        return x, torch.tensor(float(row["label"]))


def threshold_for(y, p):
    precision, recall, thresholds = precision_recall_curve(y, p)
    i = max(
        range(len(thresholds)),
        key=lambda i: (
            min(precision[i], recall[i]),
            2 * precision[i] * recall[i] / max(precision[i] + recall[i], 1e-12),
        ),
    )
    return float(thresholds[i])


def evaluate(y, p, threshold):
    y = np.asarray(y, dtype=int)
    p = np.asarray(p)
    pred = p >= threshold
    tp = int(((y == 1) & pred).sum())
    fp = int(((y == 0) & pred).sum())
    fn = int(((y == 1) & ~pred).sum())
    tn = int(((y == 0) & ~pred).sum())
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)

    def wilson(k, n):
        z = 1.959963984540054
        phat = k / n
        den = 1 + z * z / n
        mid = (phat + z * z / (2 * n)) / den
        half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / den
        return [max(0, mid - half), min(1, mid + half)]

    return {
        "rows": len(y),
        "threshold": threshold,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / max(precision + recall, 1e-12),
        "false_positive_rate": fp / max(fp + tn, 1),
        "pr_auc": float(average_precision_score(y, p)),
        "roc_auc": float(roc_auc_score(y, p)),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision_95ci": wilson(tp, max(tp + fp, 1)),
        "recall_95ci": wilson(tp, max(tp + fn, 1)),
    }


def main():
    started = time.monotonic()
    torch.set_num_threads(4)
    torch.manual_seed(42)
    np.random.seed(42)
    if DEVICE == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("MPS GPU unavailable; run with approved native GPU access")
    records_digest = hashlib.sha256((ROOT / "records-private.json").read_bytes()).hexdigest()
    rows = json.loads((ROOT / "records-private.json").read_text())
    loaders = {}
    for phase in ("train", "selection", "calibration", "test"):
        selected = [r for r in rows if r["phase"] == phase]
        loaders[phase] = torch.utils.data.DataLoader(
            Images(selected, phase == "train"),
            batch_size=16,
            shuffle=phase == "train",
            num_workers=0,
            persistent_workers=False,
            generator=torch.Generator().manual_seed(42),
        )
    if (
        hashlib.sha256(PRETRAINED.read_bytes()).hexdigest()
        != "f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec"
    ):
        raise ValueError("ImageNet weights fingerprint mismatch")
    net = resnet18(weights=None)
    net.load_state_dict(torch.load(PRETRAINED, weights_only=True, map_location="cpu"))
    net.fc = nn.Sequential(
        nn.Dropout(0.3), nn.Linear(512, 128), nn.ReLU(), nn.Dropout(0.2), nn.Linear(128, 1)
    )
    for parameter in net.parameters():
        parameter.requires_grad = False
    for module in (net.layer3, net.layer4, net.fc):
        for parameter in module.parameters():
            parameter.requires_grad = True
    net.to(DEVICE)
    optimizer = torch.optim.AdamW(
        [
            {"params": list(net.layer3.parameters()) + list(net.layer4.parameters()), "lr": 1e-4},
            {"params": net.fc.parameters(), "lr": 1e-3},
        ],
        weight_decay=1e-4,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=20, eta_min=1e-6)
    training = [r for r in rows if r["phase"] == "train"]
    weight = sum(r["label"] == 0 for r in training) / sum(r["label"] == 1 for r in training)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([weight], device=DEVICE))

    def score(phase, device=DEVICE):
        net.eval()
        actual = []
        scores = []
        with torch.inference_mode():
            for x, y in loaders[phase]:
                scores.extend(torch.sigmoid(net(x.to(device))).cpu().flatten().tolist())
                actual.extend(y.int().tolist())
        return actual, scores

    best = -1
    stale = 0
    history = []
    best_epoch = 0
    for epoch in range(20):
        net.train()
        for frozen in (net.bn1, net.layer1, net.layer2):
            frozen.eval()
        total = 0
        seen = 0
        for i, (x, y) in enumerate(loaders["train"]):
            x = x.to(DEVICE)
            y = y.to(DEVICE).reshape(-1, 1)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(net(x), y)
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 5)
            optimizer.step()
            total += float(loss.detach().cpu()) * len(x)
            seen += len(x)
            if i % 50 == 0:
                print(
                    json.dumps(
                        {
                            "epoch": epoch + 1,
                            "trained_rows": seen,
                            "seconds": round(time.monotonic() - started, 1),
                        }
                    ),
                    flush=True,
                )
        scheduler.step()
        y, p = score("selection")
        ap = float(average_precision_score(y, p))
        m = evaluate(y, p, threshold_for(y, p))
        row = {
            "epoch": epoch + 1,
            "train_loss": total / seen,
            "selection_pr_auc": ap,
            "selection_precision": m["precision"],
            "selection_recall": m["recall"],
            "seconds": round(time.monotonic() - started, 1),
        }
        history.append(row)
        print(json.dumps(row), flush=True)
        if ap > best + 1e-5:
            best = ap
            stale = 0
            best_epoch = epoch + 1
            with (ROOT / "best.pt").open("wb") as stream:
                torch.save({k: v.detach().cpu() for k, v in net.state_dict().items()}, stream)
        else:
            stale += 1
        (ROOT / "training-history.json").write_text(json.dumps(history, indent=2) + "\n")
        if stale >= 5 and epoch >= 7:
            break
    digest = hashlib.sha256((ROOT / "best.pt").read_bytes()).hexdigest()
    lock = {
        "architecture": "resnet18-finetune-v1",
        "weights_sha256": digest,
        "best_epoch": best_epoch,
        "selection_pr_auc": best,
        "epochs": len(history),
        "seed": 42,
        "records_sha256": records_digest,
        "training_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "rule": "Maximum selection PR AUC; calibration and test not scored before selection lock.",
    }
    assert (
        hashlib.sha256((ROOT / "records-private.json").read_bytes()).hexdigest() == records_digest
    )
    (ROOT / "selection-lock.json").write_text(json.dumps(lock, indent=2) + "\n")
    net.load_state_dict(torch.load(ROOT / "best.pt", weights_only=True, map_location="cpu"))
    net.to("cpu")
    y, p = score("calibration", "cpu")
    threshold = threshold_for(y, p)
    calibration = evaluate(y, p, threshold)
    (ROOT / "threshold-lock.json").write_text(
        json.dumps(
            {
                "weights_sha256": digest,
                "threshold": threshold,
                "policy": "Maximize minimum phishing precision and recall on calibration only.",
                "calibration": calibration,
            },
            indent=2,
        )
        + "\n"
    )
    y, p = score("test", "cpu")
    test = evaluate(y, p, threshold)
    np.savez_compressed(ROOT / "test-predictions-private.npz", labels=y, scores=p)
    report = {
        **lock,
        "model_version": "experimental-cnn-v1-" + digest[:12],
        "threshold": threshold,
        "class_polarity": "0=legitimate,1=phishing",
        "calibration": calibration,
        "held_out_test": test,
        "target_met_on_test": min(test["precision"], test["recall"]) >= 0.85,
        "data": json.loads((ROOT / "preparation.json").read_text()),
        "training_history": history,
        "positive_class_weight": weight,
        "device": DEVICE,
        "evaluation_device": "cpu",
        "seconds": time.monotonic() - started,
        "limitations": "Publisher/source-specific evaluation, not certification for all live websites. Previous PhishGuard test is a different corpus; do not compare headline numbers as identical cohorts.",
    }
    (ROOT / "evaluation.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "complete": True,
                "calibration": calibration,
                "held_out_test": test,
                "target_met": report["target_met_on_test"],
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
