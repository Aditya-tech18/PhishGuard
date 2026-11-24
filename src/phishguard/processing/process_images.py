"""Offline image validation and metadata; no page downloads or screenshot collection."""

import hashlib
import io
import warnings
from pathlib import Path


def validate_image(data, max_bytes=5_000_000):
    from PIL import Image, UnidentifiedImageError

    if not 0 < len(data) <= max_bytes:
        raise ValueError("Image is empty or exceeds byte limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {"PNG", "JPEG"}:
                    raise ValueError("Only PNG and JPEG are supported")
                width, height = image.size
                if not 1 <= width * height <= 16_000_000:
                    raise ValueError("Image exceeds pixel limit")
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                return image.convert("RGB")
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        OverflowError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as exc:
        raise ValueError("Invalid image") from exc


def image_inventory(root):
    root = Path(root).resolve(strict=True)
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlink in image dataset")
        if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue
        try:
            if path.stat().st_size > 5_000_000:
                raise ValueError("Image too large")
            data = path.read_bytes()
            image = validate_image(data)
            yield {
                "path": str(path.relative_to(root)),
                "width": image.width,
                "height": image.height,
                "sha256": hashlib.sha256(data).hexdigest(),
                "valid": True,
            }
        except ValueError:
            yield {"path": str(path.relative_to(root)), "valid": False}
