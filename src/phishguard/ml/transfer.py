"""Fixed ResNet18 transfer architectures and bounded numeric heads.

Inference never downloads weights. Training explicitly supplies the official pretrained file.
Torchvision model code is used under its upstream license; ImageNet initialization is not a
claim that the resulting phishing classifier is independently certified or calibrated.
"""

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from torchvision.models import resnet18
from phishguard.processing.process_images import validate_image

TRANSFER_ARCHITECTURES = {
    "resnet18-finetune-v1",
    "resnet18-frozen-linear-v1",
    "resnet18-frozen-rbf-v1",
}
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
FEATURES = 2816


class ResNetFeatures(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = resnet18(weights=None)
        self.backbone.fc = nn.Identity()

    def forward(self, x):
        b = self.backbone
        x = b.maxpool(b.relu(b.bn1(b.conv1(x))))
        x = b.layer2(b.layer1(x))
        middle = b.layer3(x)
        last = b.layer4(middle)
        # Input is fixed to 224px: layer4 is 7x7. This equals adaptive pooling to 2x2,
        # including overlap, while supporting the Metal backend during feature extraction.
        spatial = F.avg_pool2d(last, kernel_size=4, stride=3)
        return torch.cat(
            [
                F.adaptive_avg_pool2d(middle, 1).flatten(1),
                F.adaptive_avg_pool2d(last, 1).flatten(1),
                spatial.flatten(1),
            ],
            dim=1,
        )


class FrozenTransfer(nn.Module):
    def __init__(self, kind, components=256, support_vectors=0):
        super().__init__()
        if kind not in {"linear", "rbf"}:
            raise ValueError("Unsupported transfer head")
        if kind == "rbf" and (
            type(components) is not int
            or not 1 <= components <= 512
            or type(support_vectors) is not int
            or not 1 <= support_vectors <= 20000
        ):
            raise ValueError("Transfer head dimensions exceed bounds")
        self.features = ResNetFeatures()
        self.kind = kind
        self.register_buffer("feature_mean", torch.zeros(FEATURES))
        self.register_buffer("feature_scale", torch.ones(FEATURES))
        self.register_buffer("intercept", torch.zeros(1))
        if kind == "linear":
            self.register_buffer("coef", torch.zeros(1, FEATURES))
        else:
            self.register_buffer("pca_mean", torch.zeros(FEATURES))
            self.register_buffer("pca_components", torch.zeros(components, FEATURES))
            self.register_buffer("support_vectors", torch.zeros(support_vectors, components))
            self.register_buffer("dual_coef", torch.zeros(1, support_vectors))
            self.register_buffer("gamma", torch.ones(()))

    def forward(self, x):
        features = (self.features(x) - self.feature_mean) / self.feature_scale
        if self.kind == "linear":
            return features @ self.coef.T + self.intercept
        projected = (features - self.pca_mean) @ self.pca_components.T
        projected = F.normalize(projected, p=2, dim=1)
        squared = (
            (projected * projected).sum(1, keepdim=True)
            + (self.support_vectors * self.support_vectors).sum(1).unsqueeze(0)
            - 2 * projected @ self.support_vectors.T
        )
        kernel = torch.exp(-self.gamma * torch.clamp(squared, min=0))
        return kernel @ self.dual_coef.T + self.intercept


def validate_transfer_state(net):
    if isinstance(net, FrozenTransfer):
        if (net.feature_scale <= 0).any():
            raise ValueError("Transfer scales must be positive")
        if net.kind == "rbf" and not 0 < float(net.gamma) <= 1e6:
            raise ValueError("Invalid RBF gamma")


def build_transfer(variant, report=None):
    """Construct only a fixed allowlisted graph; JSON cannot supply executable layers."""
    if variant not in TRANSFER_ARCHITECTURES:
        raise ValueError("Unsupported transfer architecture")
    if variant == "resnet18-finetune-v1":
        network = resnet18(weights=None)
        network.fc = nn.Sequential(
            nn.Dropout(0.3), nn.Linear(512, 128), nn.ReLU(), nn.Dropout(0.2), nn.Linear(128, 1)
        )
        return network
    kind = "linear" if variant.endswith("linear-v1") else "rbf"
    dimensions = (report or {}).get("head", {})
    if not isinstance(dimensions, dict):
        raise ValueError("Transfer head dimensions must be an object")
    components = dimensions.get("components", 256)
    supports = dimensions.get("support_vectors", 0)
    if kind == "rbf" and (
        type(components) is not int
        or not 1 <= components <= 512
        or type(supports) is not int
        or not 1 <= supports <= 10000
    ):
        raise ValueError("Transfer support/head dimensions exceed limits")
    return FrozenTransfer(kind, components, supports)


def transfer_tensor(data):
    """Runtime transform exactly matches the training derivative plus normalization."""
    from PIL import Image

    image = validate_image(data).resize((224, 224), resample=Image.Resampling.BILINEAR)
    array = np.asarray(image, dtype=np.uint8).copy()
    tensor = torch.from_numpy(array).permute(2, 0, 1).to(torch.float32).mul_(1.0 / 255.0)
    return (tensor - torch.tensor(MEAN).view(3, 1, 1)) / torch.tensor(STD).view(3, 1, 1)
