"""Read only inert images and publisher metadata from an AES ZIP.

Original archive and the Desktop project are never modified. No HTML is extracted.
"""

from pathlib import Path
from collections import Counter, defaultdict
from io import BytesIO
from urllib.parse import urlsplit
import hashlib
import json
import os
import time

import pyzipper
from PIL import Image, ImageOps
import tldextract
from sklearn.model_selection import GroupShuffleSplit
import numpy as np

ROOT = Path(os.environ.get("PHISH360_WORK_DIR", "reports/private-phish360"))
ARCHIVE = Path(os.environ.get("PHISH360_ARCHIVE", "data/raw/phish360/phish360.zip"))
PHISHING_BRANDS = set(
    "santander sparkasse itau orange xfinity impots irs boa adobe dropbox chase office cibc bradesco alibaba facebook amazon yahoo google ebay aol att linkedin microsoft dhl paypal amex apple sfr navy match hsbc wellsfargo outlook netflix caixa tmobile mic usaa natwest bmo nab bt capitalone cox alllegro".split()
)


def main(password):
    started = time.monotonic()
    cache = ROOT / "images224"
    cache.mkdir(mode=0o700, exist_ok=True)
    if os.environ.get("PHISH360_REUSE_DECODED") == "1":
        finish(
            json.loads((ROOT / "decoded-records-private.json").read_text()),
            json.loads((ROOT / "decode-rejections-private.json").read_text()),
            10748,
            started,
        )
        return
    extract = tldextract.TLDExtract(
        suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True
    )
    rows, rejected = [], []
    Image.MAX_IMAGE_PIXELS = 20_000_000
    with pyzipper.AESZipFile(ARCHIVE) as archive:
        archive.setpassword(password)
        members = sorted(
            n for n in archive.namelist() if n.endswith("/SCREEN-SHOT/screen_shoot.png")
        )
        for index, name in enumerate(members):
            base = name.rsplit("/SCREEN-SHOT/", 1)[0]
            try:
                for member, bound in (
                    (base + "/Label/label.txt", 1024),
                    (base + "/URL/url.txt", 16384),
                    (name, 32_000_000),
                ):
                    if archive.getinfo(member).file_size > bound:
                        raise ValueError("Archive member exceeds fixed byte limit")
                label_text = (
                    archive.read(base + "/Label/label.txt").decode("utf-8-sig").strip().lower()
                )
                # Publisher training positives carry a brand label; test positives say phish.
                # Require the explicit brand allowlist AND consistent publisher P-folder encoding.
                folder = base.split("/")[-1]
                brand_positive = (
                    base.split("/")[1] == "trainval"
                    and folder.startswith("P")
                    and label_text in PHISHING_BRANDS
                    and folder.rsplit("_", 1)[-1] == label_text
                )
                if label_text not in ("legitimate", "phish", "phishing") and not brand_positive:
                    raise ValueError("Unrecognized publisher label: " + repr(label_text))
                if (label_text == "legitimate") != folder.startswith("L"):
                    raise ValueError("Publisher label/folder class mismatch")
                url = archive.read(base + "/URL/url.txt").decode("utf-8-sig").strip()
                parsed = urlsplit(url if "://" in url else "https://" + url)
                host = (parsed.hostname or "").lower().rstrip(".")
                if not host or any(c.isspace() for c in host):
                    raise ValueError("Invalid URL hostname")
                domain = extract(host).top_domain_under_public_suffix or host
                raw = archive.read(name)
                digest = hashlib.sha256(raw).hexdigest()
                with Image.open(BytesIO(raw)) as image:
                    width, height = image.size
                    if min(width, height) < 64:
                        raise ValueError("Screenshot smaller than 64 pixels")
                    if width * height > 20_000_000:
                        raise ValueError("Screenshot exceeds fixed 20-million-pixel resource bound")
                    image.load()
                    rgb = ImageOps.exif_transpose(image).convert("RGB")
                    small = rgb.resize((224, 224), Image.Resampling.BILINEAR)
                    pixel = hashlib.sha256(small.tobytes()).hexdigest()
                    # Match the earlier corpus audit transform without loading old raw images.
                    old_pixel = hashlib.sha256(
                        rgb.resize((128, 128), Image.Resampling.BICUBIC).tobytes()
                    ).hexdigest()
                    destination = cache / (digest + ".png")
                    if not destination.exists():
                        small.save(destination)
                        destination.chmod(0o600)
                rows.append(
                    {
                        "member": name,
                        "label": int(label_text != "legitimate"),
                        "publisher_label": label_text,
                        "split": name.split("/")[1],
                        "domain": domain,
                        "host": host,
                        "sha256": digest,
                        "pixel_hash": pixel,
                        "old_pixel_hash": old_pixel,
                        "cache_path": str(destination),
                        "original_size": [width, height],
                    }
                )
            except (
                ValueError,
                OSError,
                UnicodeError,
                KeyError,
                Image.DecompressionBombError,
            ) as exc:
                rejected.append({"member": name, "reason": str(exc)})
            if index % 500 == 0:
                print(
                    json.dumps(
                        {
                            "prepared": index,
                            "total": len(members),
                            "seconds": round(time.monotonic() - started, 1),
                        }
                    ),
                    flush=True,
                )
    (ROOT / "decoded-records-private.json").write_text(json.dumps(rows))
    (ROOT / "decode-rejections-private.json").write_text(json.dumps(rejected))
    finish(rows, rejected, len(members), started)


def finish(rows, rejected, member_count, started):
    if len(rows) + len(rejected) != 10748:
        raise ValueError("Unexpected archive screenshot count")
    # Join domains linked by identical pixels, so all connected components stay together.
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)

    pixels = defaultdict(list)
    for row in rows:
        pixels[row["pixel_hash"]].append(row)
        find(row["domain"])
    for bucket in pixels.values():
        for row in bucket[1:]:
            union(bucket[0]["domain"], row["domain"])
    exclusions = Counter()
    clean = []
    for bucket in pixels.values():
        if len({r["label"] for r in bucket}) > 1:
            exclusions["conflicting_label_pixels"] += len(bucket)
            continue
        # Prefer official test for duplicates crossing official split boundaries.
        bucket.sort(key=lambda r: (r["split"] != "test", r["sha256"], r["member"]))
        clean.append(bucket[0])
        exclusions["exact_pixel_duplicates"] += len(bucket) - 1
    for row in clean:
        row["group"] = hashlib.sha256(find(row["domain"]).encode()).hexdigest()
    test_groups = {r["group"] for r in clean if r["split"] == "test"}
    filtered = []
    for row in clean:
        if row["split"] != "test" and row["group"] in test_groups:
            exclusions["trainval_group_overlaps_official_test"] += 1
        else:
            filtered.append(row)
    development = [r for r in filtered if r["split"] == "trainval"]

    def split_group(records, size, seed):
        a, b = next(
            GroupShuffleSplit(n_splits=1, test_size=size, random_state=seed).split(
                np.zeros(len(records)), [r["label"] for r in records], [r["group"] for r in records]
            )
        )
        return [records[i] for i in a], [records[i] for i in b]

    training, val = split_group(development, 0.3, 4201)
    selection, calibration = split_group(val, 0.5, 4202)
    phases = {
        "train": training,
        "selection": selection,
        "calibration": calibration,
        "test": [r for r in filtered if r["split"] == "test"],
    }
    print(
        json.dumps(
            {
                "fold_counts": {
                    p: dict(Counter(r["label"] for r in rs)) for p, rs in phases.items()
                },
                "pre_split_exclusions": dict(exclusions),
            }
        ),
        flush=True,
    )
    for phase, records in phases.items():
        if len({r["label"] for r in records}) != 2:
            raise ValueError("A fold does not contain both classes")
        for row in records:
            row["phase"] = phase
    for a in phases:
        for b in phases:
            if a != b:
                assert not {r["group"] for r in phases[a]} & {r["group"] for r in phases[b]}
    old_path = Path(
        os.environ.get(
            "PHISH360_PREVIOUS_MANIFEST",
            str(ROOT.parent / "vision-transfer/clean-records-private.json"),
        )
    )
    old = json.loads(old_path.read_text()) if old_path.is_file() else []
    old_hashes = {r["sha256"] for r in old}
    old_pixels = {r["pixel_hash"] for r in old}
    old_overlap = sum(
        r["sha256"] in old_hashes or r["old_pixel_hash"] in old_pixels for r in filtered
    )
    report = {
        "source": str(ARCHIVE),
        "publisher": "Phish360/CrossPhire",
        "input_screenshots": member_count,
        "decoded_screenshots": len(rows),
        "label_mapping": "legitimate=0; phish/phishing=1; trainval P-prefixed folders with an exact matching allowlisted brand label=1. Missing/unknown/mismatched labels excluded. Brand strings never enter the model.",
        "rejected_count": len(rejected),
        "exclusions": dict(exclusions),
        "counts": {
            p: dict(Counter("phishing" if r["label"] else "legitimate" for r in rs))
            for p, rs in phases.items()
        },
        "old_corpus_exact_overlap": old_overlap,
        "previous_corpus_overlap_audited": bool(old),
        "old_corpus_used_for_training": False,
        "policy": "Official test retained; trainval domains/content components intersecting test excluded. Selection/calibration split by registrable-domain/pixel components, seeds 4201/4202. Labels and image validity checked before modeling. No outcome-based filtering.",
        "initialization": "Official ImageNet weights only; old PhishGuard tuned weights excluded.",
        "input": "Full-frame RGB224 bilinear, ImageNet normalization; no filename, URL, label text, or brand as input.",
        "limitations": "Publisher labels not independently verified. Exact dedup does not remove every near-duplicate template. This is an in-source domain-isolated benchmark, not universal live-web certification.",
        "seconds": time.monotonic() - started,
    }
    (ROOT / "records-private.json").write_text(
        json.dumps([r for rs in phases.values() for r in rs])
    )
    (ROOT / "rejected-private.json").write_text(json.dumps(rejected))
    (ROOT / "preparation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main(os.environ["PHISH360_DATASET_PASSWORD"].encode())
