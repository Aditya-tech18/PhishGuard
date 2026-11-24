import csv
import pytest

pytestmark = pytest.mark.vision


def images(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    root = tmp_path / "images"
    root.mkdir()
    rows = []
    for split, colors in [("train", ["red", "blue"]), ("val", ["green", "yellow"])]:
        for label, color in enumerate(colors):
            name = f"{split}-{label}.png"
            Image.new("RGB", (16, 16), color).save(root / name)
            rows.append(
                {"path": name, "label": str(label), "split": split, "group": split + str(label)}
            )
    return root, rows


def manifest(tmp_path, rows):
    path = tmp_path / "manifest.csv"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["path", "label", "split", "group"])
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_lazy_manifest_and_group_summary(tmp_path):
    pytest.importorskip("torch")
    from phishguard.ml.vision_dataset import read_manifest, LazyImages, summary

    root, rows = images(tmp_path)
    records = read_manifest(root, manifest(tmp_path, rows))
    dataset = LazyImages(records, "train")
    assert len(dataset) == 2
    x, y = dataset[0]
    assert tuple(x.shape) == (3, 128, 128)
    assert y.item() == 0
    report = summary(records)
    assert report["explicit_group_isolation"] is True
    assert report["rows"] == 4
    assert "path" not in str(report)


@pytest.mark.parametrize("kind", ["group", "bytes", "path", "label"])
def test_manifest_leakage_and_traversal_rejected(tmp_path, kind):
    from phishguard.ml.vision_dataset import read_manifest

    root, rows = images(tmp_path)
    if kind == "group":
        rows[2]["group"] = rows[0]["group"]
    elif kind == "bytes":
        (root / rows[2]["path"]).write_bytes((root / rows[0]["path"]).read_bytes())
    elif kind == "path":
        rows[0]["path"] = "../outside.png"
    else:
        rows[0]["label"] = "unknown"
    with pytest.raises(ValueError):
        read_manifest(root, manifest(tmp_path, rows))
