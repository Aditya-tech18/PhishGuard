"""Supervised transfer learning with separate selection, calibration and test folds.

The training entry point never runs inside the HTTP API. It requires a trusted explicit
image manifest and a local official pretrained state file. It does not fetch user URLs.
"""

import hashlib
import math
from pathlib import Path
from tempfile import NamedTemporaryFile
import numpy as np
from phishguard.common.files import read_json, reject_symlink_chain, atomic_json
from phishguard.ml.evaluate_models import evaluate


def choose_balanced_threshold(labels, scores):
    from sklearn.metrics import precision_recall_curve

    labels, scores = np.asarray(labels), np.asarray(scores)
    if (
        labels.shape != scores.shape
        or set(labels.tolist()) != {0, 1}
        or not np.isfinite(scores).all()
        or ((scores < 0) | (scores > 1)).any()
    ):
        raise ValueError("Aligned finite scores and both classes required")
    precision, recall, thresholds = precision_recall_curve(labels, scores)
    if not len(thresholds):
        raise ValueError("No threshold candidates")
    index = max(
        range(len(thresholds)),
        key=lambda i: (
            min(precision[i], recall[i]),
            2 * precision[i] * recall[i] / max(precision[i] + recall[i], 1e-12),
        ),
    )
    return float(np.clip(thresholds[index], 1e-6, 1 - 1e-6))


def _save_tensors(path, state):
    import torch

    path = Path(path)
    with NamedTemporaryFile(dir=path.parent, prefix=".transfer-", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with temporary.open("wb") as stream:
            torch.save(state, stream)
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _wilson(successes, total):
    if not total:
        return None
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    radius = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    return [max(0.0, center - radius), min(1.0, center + radius)]


def intervals(metrics):
    counts = metrics["confusion"]
    return {
        "method": "Wilson 95% intervals, individual examples; not domain-bootstrap intervals",
        "precision": _wilson(counts["tp"], counts["tp"] + counts["fp"]),
        "recall": _wilson(counts["tp"], counts["tp"] + counts["fn"]),
    }


class TransferImages:
    """Picklable lazy derivatives, with the exact float augmentation recipe used in trials."""

    def __init__(self, rows, augment=False):
        import torch
        from torchvision.transforms import v2 as transforms

        self.rows = rows
        operations = [transforms.ToImage(), transforms.ToDtype(torch.float32, scale=True)]
        if augment:
            operations += [
                transforms.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.05),
                transforms.RandomAffine(
                    degrees=0, translate=(0.015, 0.015), scale=(0.97, 1.03), fill=1.0
                ),
            ]
        operations += [transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225))]
        self.transform = transforms.Compose(operations)

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        import torch
        from phishguard.processing.process_images import validate_image

        row = self.rows[index]
        image = validate_image(Path(row["cache_path"]).read_bytes())
        if image.size != (224, 224):
            raise ValueError("Expected verified 224px transfer derivative")
        return self.transform(image), torch.tensor(float(row["label"]))


def train_transfer(
    records_file,
    pretrained,
    output,
    epochs=16,
    batch_size=32,
    patience=4,
    device="cpu",
    workers=0,
    freeze_batchnorm=False,
    progress=None,
):
    """Train on train, choose checkpoint on selection, threshold on calibration, then test once."""
    import torch
    from torch import nn
    from torch.utils.data import DataLoader
    from torchvision.models import resnet18
    from sklearn.metrics import average_precision_score

    if (
        type(epochs) is not int
        or not 1 <= epochs <= 100
        or type(batch_size) is not int
        or not 1 <= batch_size <= 64
        or type(patience) is not int
        or not 1 <= patience <= 20
        or type(workers) is not int
        or not 0 <= workers <= 8
    ):
        raise ValueError("Invalid transfer training bounds")
    if device not in {"cpu", "mps", "cuda"}:
        raise ValueError("Unsupported device")
    if device == "mps" and not torch.backends.mps.is_available():
        raise ValueError("MPS is unavailable")
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA is unavailable")
    torch.set_num_threads(4)
    torch.manual_seed(42)
    output = reject_symlink_chain(Path(output).absolute())
    if output.exists():
        raise ValueError("Training output must be a fresh directory")
    pretrained = reject_symlink_chain(pretrained)
    if not 1 <= pretrained.stat().st_size <= 64_000_000:
        raise ValueError("Expected bounded local ResNet18 initialization")
    digest = hashlib.sha256(pretrained.read_bytes()).hexdigest()
    if not digest.startswith("f37072fd"):
        raise ValueError("Expected official ResNet18 ImageNet-1K V1 weight fingerprint")
    records = read_json(records_file, max_bytes=64_000_000)["records"]
    subsets = {
        phase: [row for row in records if row["phase"] == phase]
        for phase in ["train", "selection", "calibration", "test"]
    }
    group_sets = {}
    for phase in ["train", "selection", "calibration"]:
        if {row["label"] for row in subsets[phase]} != {0, 1}:
            raise ValueError("Both classes required in train, selection and calibration")
    for phase, rows in subsets.items():
        group_sets[phase] = {row["group"] for row in rows}
        if any(group_sets[phase] & other for key, other in group_sets.items() if key != phase):
            raise ValueError("Transfer domain leakage")
        for row in rows:
            path = reject_symlink_chain(row["cache_path"])
            if path.suffix != ".png" or not 0 < path.stat().st_size <= 5_000_000:
                raise ValueError("Expected bounded private PNG derivatives")
    output.mkdir(parents=True, mode=0o700)
    loaders = {
        phase: DataLoader(
            TransferImages(subsets[phase], augment=phase == "train"),
            batch_size=batch_size,
            shuffle=phase == "train",
            num_workers=workers,
            persistent_workers=workers > 0,
            generator=torch.Generator().manual_seed(42),
        )
        for phase in subsets
        if subsets[phase]
    }
    network = resnet18(weights=None)
    network.load_state_dict(torch.load(pretrained, weights_only=True, map_location="cpu"))
    network.fc = nn.Sequential(
        nn.Dropout(0.3), nn.Linear(512, 128), nn.ReLU(), nn.Dropout(0.2), nn.Linear(128, 1)
    )
    for parameter in network.parameters():
        parameter.requires_grad = False
    for layer in [network.layer3, network.layer4, network.fc]:
        for parameter in layer.parameters():
            parameter.requires_grad = True
    network.to(device)
    optimizer = torch.optim.AdamW(
        [
            {
                "params": list(network.layer3.parameters()) + list(network.layer4.parameters()),
                "lr": 1e-4,
            },
            {"params": network.fc.parameters(), "lr": 1e-3},
        ],
        weight_decay=1e-4,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-6)
    labels = [row["label"] for row in subsets["train"]]
    positive_weight = labels.count(0) / labels.count(1)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([positive_weight], device=device))
    history, best, stale = [], -1.0, 0
    best_path = output / "selected-checkpoint.pt"

    def score(phase):
        network.eval()
        actual, scores = [], []
        with torch.inference_mode():
            for x, y in loaders[phase]:
                scores.extend(torch.sigmoid(network(x.to(device))).cpu().flatten().tolist())
                actual.extend(y.int().tolist())
        return actual, scores

    for epoch in range(epochs):
        network.train()
        for layer in [network.bn1, network.layer1, network.layer2]:
            layer.eval()
        if freeze_batchnorm:
            for layer in network.modules():
                if isinstance(layer, nn.BatchNorm2d):
                    layer.eval()
        total, count = 0.0, 0
        for x, y in loaders["train"]:
            x, y = x.to(device), y.to(device).reshape(-1, 1)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(network(x), y)
            if not torch.isfinite(loss):
                raise ValueError("Non-finite transfer loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(network.parameters(), 5.0)
            optimizer.step()
            total += float(loss.detach().cpu()) * len(x)
            count += len(x)
        scheduler.step()
        actual, scores = score("selection")
        ap = float(average_precision_score(actual, scores))
        row = {"epoch": epoch + 1, "train_loss": total / count, "selection_pr_auc": ap}
        history.append(row)
        if progress:
            progress(row)
        if ap > best + 1e-5:
            best, stale = ap, 0
            _save_tensors(
                best_path,
                {key: value.detach().cpu() for key, value in network.state_dict().items()},
            )
        else:
            stale += 1
        # Private interruption checkpoint; never packaged or loaded by the API.
        _save_tensors(
            output / "last-training-checkpoint.pt",
            {
                "epoch": epoch + 1,
                "network": {
                    key: value.detach().cpu() for key, value in network.state_dict().items()
                },
                "history": history,
                "scheduler": scheduler.state_dict(),
            },
        )
        if stale >= patience and epoch >= 5:
            break
    network.load_state_dict(torch.load(best_path, weights_only=True, map_location=device))
    actual, scores = score("calibration")
    threshold = choose_balanced_threshold(actual, scores)
    model_path = output / "vision-model.pt"
    _save_tensors(
        model_path, {key: value.detach().cpu() for key, value in network.state_dict().items()}
    )
    fingerprint = hashlib.sha256(model_path.read_bytes()).hexdigest()
    report = {
        "architecture": "resnet18-finetune-v1",
        "weights_sha256": fingerprint,
        "model_version": "experimental-cnn-v1-" + fingerprint[:12],
        "threshold": threshold,
        "pretrained_sha256": digest,
        "pretrained_source": "https://download.pytorch.org/models/resnet18-f37072fd.pth",
        "selection_policy": "checkpoint PR AUC on selection only; max-min precision/recall threshold on separate calibration only",
        "history": history,
        "seed": 42,
        "device": device,
        "freeze_batchnorm": freeze_batchnorm,
        "positive_class_weight": positive_weight,
        "calibration": evaluate(actual, scores, threshold),
        "class_polarity": "0=legitimate, 1=phishing",
        "target_precision_recall": 0.85,
        "limitations": "Experimental image-only classifier; inherited labels/groups need independent verification. Scores are not calibrated safety probabilities.",
    }
    report["calibration_intervals"] = intervals(report["calibration"])
    if subsets["test"]:
        actual, scores = score("test")
        report["held_out_test"] = evaluate(actual, scores, threshold)
        report["held_out_test_intervals"] = intervals(report["held_out_test"])
        report["target_met_on_test"] = (
            min(report["held_out_test"]["precision"], report["held_out_test"]["recall"]) >= 0.85
        )
    atomic_json(model_path.with_suffix(".json"), report)
    return report
