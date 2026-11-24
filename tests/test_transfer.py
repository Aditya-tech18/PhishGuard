"""CPU-only transfer inference tests; never download pretrained data in the test suite."""

import hashlib
import io
import json
import pytest

pytestmark = pytest.mark.vision


def test_transfer_preprocessing_matches_training_derivative(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("torchvision")
    import numpy as np
    from PIL import Image
    from torchvision.transforms import v2 as T
    from phishguard.ml.transfer import transfer_tensor, MEAN, STD

    image = Image.fromarray(
        np.random.default_rng(42).integers(0, 255, (311, 517, 3), dtype=np.uint8)
    )
    data = io.BytesIO()
    image.save(data, format="PNG")
    derivative = image.resize((224, 224), resample=Image.Resampling.BILINEAR)
    expected = T.Compose(
        [T.ToImage(), T.ToDtype(torch.float32, scale=True), T.Normalize(MEAN, STD)]
    )(derivative)
    assert torch.equal(transfer_tensor(data.getvalue()), expected)


def test_transfer_pooling_has_exact_adaptive_semantics():
    torch = pytest.importorskip("torch")
    pytest.importorskip("torchvision")
    from torch.nn import functional as F

    x = torch.rand(2, 512, 7, 7)
    assert torch.allclose(F.avg_pool2d(x, 4, 3), F.adaptive_avg_pool2d(x, 2))


def test_transfer_weight_identity_and_offline_roundtrip(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("torchvision")
    from PIL import Image
    from phishguard.ml.transfer import build_transfer
    from phishguard.ml.vision import VisionModel

    torch.set_num_threads(2)
    network = build_transfer("resnet18-finetune-v1").eval()
    path = tmp_path / "transfer.pt"
    torch.save(network.state_dict(), path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    report = {
        "architecture": "resnet18-finetune-v1",
        "weights_sha256": digest,
        "model_version": "experimental-cnn-v1-" + digest[:12],
        "threshold": 0.6,
    }
    path.with_suffix(".json").write_text(json.dumps(report))
    data = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(data, format="PNG")
    result = VisionModel(path).predict(data.getvalue())
    assert 0 <= result["probability"] <= 1
    assert result["model_version"] == report["model_version"]
    report["weights_sha256"] = "0" * 64
    path.with_suffix(".json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="identity"):
        VisionModel(path)


@pytest.mark.parametrize(
    "head",
    [
        {"components": 100000, "support_vectors": 2},
        {"components": 256, "support_vectors": 100000},
        {"components": 0, "support_vectors": 2},
        {"components": True, "support_vectors": 2},
    ],
)
def test_transfer_head_allocation_limits(head):
    pytest.importorskip("torch")
    pytest.importorskip("torchvision")
    from phishguard.ml.transfer import build_transfer

    with pytest.raises(ValueError, match="limits"):
        build_transfer("resnet18-frozen-rbf-v1", {"head": head})
