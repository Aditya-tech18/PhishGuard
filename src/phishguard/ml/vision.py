"""Offline small/transfer CNN inference for explicitly supplied screenshots.

No pretrained phishing claim. Input folders: train/{legitimate,phishing},
val/{legitimate,phishing}. Domain/site isolation must be prepared externally.
The model is deliberately separate from URL scoring; no unvalidated score fusion.
"""

import json
from pathlib import Path
import numpy as np
from phishguard.processing.process_images import validate_image


def architecture(variant="global-v1", configuration=None):
    if variant.startswith("resnet18-"):
        from phishguard.ml.transfer import build_transfer

        return build_transfer(variant, configuration)
    if variant not in {"global-v1", "spatial-v2"}:
        raise ValueError("Unsupported CNN architecture")
    from torch import nn

    if variant == "spatial-v2":
        return nn.Sequential(
            nn.Conv2d(3, 16, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.AdaptiveAvgPool2d((4, 4)),
            nn.Flatten(),
            nn.Dropout(0.25),
            nn.Linear(1024, 128),
            nn.ReLU(),
            nn.Dropout(0.25),
            nn.Linear(128, 1),
        )
    return nn.Sequential(
        nn.Conv2d(3, 16, 3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Conv2d(16, 32, 3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Conv2d(32, 64, 3, padding=1),
        nn.ReLU(),
        nn.AdaptiveAvgPool2d((1, 1)),
        nn.Flatten(),
        nn.Linear(64, 1),
    )


def tensor_from_bytes(data):
    import torch

    image = validate_image(data).resize((128, 128))
    array = np.asarray(image, dtype=np.float32).copy() / 255
    return torch.from_numpy(array).permute(2, 0, 1)


def train_vision(
    root,
    output,
    epochs=10,
    seed=42,
    manifest=None,
    batch_size=16,
    patience=3,
    device="cpu",
    cache_dir=None,
    progress=None,
    architecture_variant="global-v1",
):
    """Train lazily from disk; optional manifest enforces explicit site-group isolation."""
    import torch
    from torch.utils.data import DataLoader
    from phishguard.ml.vision_dataset import folder_records, read_manifest, LazyImages, summary
    from tempfile import NamedTemporaryFile
    import hashlib

    if not 1 <= epochs <= 100 or not 1 <= batch_size <= 128 or not 1 <= patience <= 20:
        raise ValueError("Invalid image training limits")
    if device not in {"cpu", "mps", "cuda"}:
        raise ValueError("Device must be cpu, mps or cuda")
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA is unavailable")
    if device == "mps" and not torch.backends.mps.is_available():
        raise ValueError("MPS is unavailable")
    import os

    threads = int(os.getenv("PHISHGUARD_TORCH_THREADS", "2"))
    if not 1 <= threads <= 8:
        raise ValueError("Torch thread count must be 1..8")
    torch.set_num_threads(threads)
    torch.manual_seed(seed)
    records = read_manifest(root, manifest) if manifest else folder_records(root)
    dataset_summary = summary(records)
    if cache_dir:
        from phishguard.ml.vision_dataset import cache_records

        records = cache_records(records, cache_dir)
    loaders = {
        split: DataLoader(
            LazyImages(records, split),
            batch_size=batch_size,
            shuffle=split == "train",
            num_workers=0,
            generator=torch.Generator().manual_seed(seed),
        )
        for split in ["train", "val"]
    }
    net = architecture(architecture_variant).to(device)
    optimizer = torch.optim.AdamW(
        net.parameters(),
        lr=3e-4 if architecture_variant == "spatial-v2" else 1e-3,
        weight_decay=1e-4,
    )
    training_labels = [record["label"] for record in records if record["split"] == "train"]
    negatives = sum(label == 0 for label in training_labels)
    positives = sum(label == 1 for label in training_labels)
    positive_weight = negatives / positives
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor([positive_weight], device=device))
    best, best_weights, history, stale = float("inf"), None, [], 0
    for epoch in range(epochs):
        net.train()
        train_loss, train_rows = 0.0, 0
        for x, y in loaders["train"]:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            loss = loss_fn(net(x), y)
            if not torch.isfinite(loss):
                raise ValueError("Image training produced non-finite loss")
            loss.backward()
            optimizer.step()
            train_loss += float(loss.detach().cpu()) * len(x)
            train_rows += len(x)
        net.eval()
        val_loss, val_rows = 0.0, 0
        with torch.no_grad():
            for x, y in loaders["val"]:
                x, y = x.to(device), y.to(device)
                val_loss += float(loss_fn(net(x), y).cpu()) * len(x)
                val_rows += len(x)
        val_loss /= val_rows
        history.append(
            {"epoch": epoch + 1, "train_loss": train_loss / train_rows, "val_loss": val_loss}
        )
        if progress is not None:
            progress(history[-1])
        if val_loss < best - 1e-8:
            best, stale = val_loss, 0
            best_weights = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
        else:
            stale += 1
            if stale >= patience:
                break
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=output.parent, prefix=".vision-", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with temporary.open("wb") as stream:
            torch.save(best_weights, stream)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    from phishguard.ml.evaluate_models import evaluate
    from phishguard.ml.select_model import select_threshold

    net.load_state_dict(best_weights)
    net.eval()
    validation_labels, validation_probabilities = [], []
    with torch.no_grad():
        for x, y in loaders["val"]:
            validation_probabilities.extend(
                torch.sigmoid(net(x.to(device))).cpu().flatten().tolist()
            )
            validation_labels.extend(y.flatten().int().tolist())
    threshold, selection = select_threshold(validation_labels, validation_probabilities)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    report = {
        "architecture": architecture_variant,
        "seed": seed,
        "device": device,
        "positive_class_weight": positive_weight,
        "history": history,
        "best_validation_loss": best,
        "dataset": dataset_summary,
        "threshold": threshold,
        "selection": selection,
        "validation": evaluate(validation_labels, validation_probabilities, threshold),
        "model_version": "experimental-cnn-v1-" + digest[:12],
        "class_polarity": "0=legitimate, 1=phishing",
        "weights_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "limitations": "Uncalibrated CNN; independent held-out site evaluation required.",
    }
    if any(r["split"] == "test" for r in records):
        from phishguard.ml.evaluate_models import evaluate

        net.load_state_dict(best_weights)
        net.eval()
        labels, probabilities = [], []
        with torch.no_grad():
            for x, y in DataLoader(LazyImages(records, "test"), batch_size=batch_size):
                probabilities.extend(torch.sigmoid(net(x.to(device))).cpu().flatten().tolist())
                labels.extend(y.flatten().int().tolist())
        report["held_out_test"] = evaluate(labels, probabilities, threshold)
    output.with_suffix(".json").write_text(json.dumps(report, indent=2, allow_nan=False))
    return report


class VisionModel:
    def __init__(self, path):
        import torch

        from phishguard.common.files import reject_symlink_chain, read_json
        import io
        import hashlib

        path = reject_symlink_chain(path)
        if not path.is_file() or path.stat().st_size > 128_000_000:
            raise ValueError("Expected bounded regular vision weights")
        with path.open("rb") as stream:
            data = stream.read(128_000_001)
        if len(data) > 128_000_000:
            raise ValueError("Vision weights exceed byte limit")
        report_path = path.with_suffix(".json")
        report = read_json(report_path) if report_path.exists() else {}
        self.architecture = report.get("architecture", "global-v1")
        self.net = architecture(self.architecture, report)
        self.net.load_state_dict(
            torch.load(io.BytesIO(data), map_location="cpu", weights_only=True)
        )
        if any(not torch.isfinite(value).all() for value in self.net.state_dict().values()):
            raise ValueError("Vision weights contain non-finite parameters")
        digest = hashlib.sha256(data).hexdigest()
        self.version = "experimental-cnn-v1-" + digest[:12]
        self.threshold = 0.5
        report_path = path.with_suffix(".json")
        if report_path.exists():
            report = read_json(report_path)
            if (
                report.get("weights_sha256") != digest
                or report.get("model_version") != self.version
            ):
                raise ValueError("Vision model/evaluation identity mismatch")
            threshold = float(report["threshold"])
            if not 0 < threshold < 1:
                raise ValueError("Invalid image threshold")
            self.threshold = threshold
        if self.architecture.startswith("resnet18-"):
            from phishguard.ml.transfer import validate_transfer_state

            validate_transfer_state(self.net)
        self.net.eval()

    def predict(self, data):
        import torch

        if self.architecture.startswith("resnet18-"):
            from phishguard.ml.transfer import transfer_tensor

            tensor = transfer_tensor(data)
        else:
            tensor = tensor_from_bytes(data)
        with torch.inference_mode():
            p = float(torch.sigmoid(self.net(tensor.unsqueeze(0))).item())
        return {
            "probability": p,
            "verdict": "phishing" if p >= self.threshold else "low_risk",
            "model_version": self.version,
            "reasons": [],
            "disclaimer": "Experimental uncalibrated image model; not a safety guarantee.",
        }
