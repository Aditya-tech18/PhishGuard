import pytest
from phishguard.ml.prepare_images import filename_domain, Components, prepare


def test_domain_parser_and_content_components():
    assert filename_domain("123_login.example.co.uk_account.png") == "example.co.uk"
    groups = Components()
    groups.join("b.test", "c.test")
    groups.join("a.test", "b.test")
    assert groups.root("c.test") == groups.root("a.test")
    with pytest.raises(ValueError):
        filename_domain("unknown.png")


def test_preparation_excludes_ambiguity_and_isolates_groups(tmp_path):
    from PIL import Image
    from phishguard.ml.vision_dataset import read_manifest

    root = tmp_path / "corpus"
    for label, directory in enumerate(["legitimate", "phishing"]):
        folder = root / directory
        folder.mkdir(parents=True)
        for index in range(40):
            Image.new("RGB", (8, 8), (index, label * 100, 10)).save(
                folder / f"{index}_site{label}-{index}.test.png"
            )
    (root / "phishing/100_conflict.test.png").write_bytes(
        (root / "legitimate/0_site0-0.test.png").read_bytes()
    )
    output = tmp_path / "prepared"
    report = prepare(root, output, filename_hosts=True)
    assert report["counts"]["ambiguous_content_groups"] == 1
    assert report["counts"]["ambiguous_content_images"] == 2
    assert report["unique_rows"] == 79
    assert report["group_overlap"] is False
    records = read_manifest(root, output / "manifest.csv")
    assert len(records) == 79
    assert all(
        any(r["split"] == name and r["label"] == label for r in records)
        for name in ["train", "val", "test"]
        for label in [0, 1]
    )
    with pytest.raises(ValueError):
        prepare(root, tmp_path / "not-opted-in")
