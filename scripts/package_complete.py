#!/usr/bin/env python3
"""Build a runnable local project bundle with explicitly selected numeric models/reports.

Unlike the GitHub-oriented source packager, this opt-in bundle includes learned artifacts.
It never includes the raw corpus, runtime sessions, environments, DBs or arbitrary model files.
"""

import argparse
import hashlib
import json
from pathlib import Path
import stat
import zipfile
from phishguard.common.files import read_json
from phishguard.ml.model_registry import URLModel
from phishguard.ml.portable import ALGORITHMS
from package_release import source_files

PRIVATE_KEYS = {
    "url",
    "urls",
    "path",
    "paths",
    "source_path",
    "api_key",
    "hmac_key",
    "session_api_key",
    "image_base64",
    "password",
    "cookies",
    "authorization",
}


def minimized(document):
    if isinstance(document, dict):
        return {
            key: minimized(value)
            for key, value in document.items()
            if key.lower() not in PRIVATE_KEYS
        }
    if isinstance(document, list):
        return [minimized(value) for value in document]
    return document


def json_bytes(document):
    return (json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def package(source, model_dir, output, quality=None, pipeline=None, vision_model=None):
    source = Path(source).resolve(strict=True)
    model_dir = Path(model_dir).resolve(strict=True)
    output = Path(output).absolute()
    if output.exists() or source in output.parents or model_dir in output.parents:
        raise ValueError("Choose a new output ZIP outside source and model directories")
    selected = URLModel.load(model_dir / "url-model.json")
    evaluation = read_json(model_dir / "evaluation.json")
    if evaluation.get("model_version") != selected.version:
        raise ValueError("Selected model and evaluation versions differ")
    contents = {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in source_files(source)
        if path.name != "MANIFEST.sha256"
    }
    source_manifest = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(contents.items())
    )
    contents["MANIFEST.sha256"] = source_manifest.encode()
    contents["models/trained/url-model.json"] = (model_dir / "url-model.json").read_bytes()
    for name, candidate in evaluation.get("candidates", {}).items():
        if name not in ALGORITHMS:
            raise ValueError("Unknown candidate name in model report")
        artifact_path = model_dir / (name + ".json")
        artifact = URLModel.load(artifact_path)
        if artifact.version != candidate["model_version"]:
            raise ValueError("Candidate model/report identity mismatch")
        contents["models/trained/candidates/" + name + ".json"] = artifact_path.read_bytes()
    contents["reports/evaluation.json"] = json_bytes(minimized(evaluation))
    if vision_model:
        from phishguard.ml.vision import VisionModel

        vision_model = Path(vision_model).resolve(strict=True)
        vision = VisionModel(vision_model)
        report = read_json(vision_model.with_suffix(".json"))
        if report.get("model_version") != vision.version:
            raise ValueError("Vision model and evaluation differ")
        contents["models/trained/vision-model.pt"] = vision_model.read_bytes()
        contents["models/trained/vision-model.json"] = json_bytes(minimized(report))
        contents["reports/vision-evaluation.json"] = json_bytes(minimized(report))
    if quality:
        contents["reports/data-quality.json"] = json_bytes(minimized(read_json(quality)))
    if pipeline:
        contents["reports/pipeline.json"] = json_bytes(minimized(read_json(pipeline)))
    contents["models/README.txt"] = (
        "Local dataset-derived numeric models. No raw dataset is included.\n"
        "Review source dataset rights before public redistribution of learned artifacts.\n"
        "The code license does not establish third-party dataset/model redistribution rights.\n"
    ).encode()
    contents["RUN_PROJECT.md"] = b"""# Run the complete local project

1. Extract this ZIP into a new folder.
2. Run `bash scripts/setup_mac.sh` with Python 3.11 available.
3. Run `source .venv/bin/activate`.
4. Run `make doctor`, then `make launch`.
5. Open the local dashboard URL printed by the launcher.
6. In Chrome open chrome://extensions, enable Developer mode, choose Load unpacked
   and select this project's extension folder. Merely copying code does not install it.
7. Open the extension toolbar popup, turn ON, and paste the transient session key
   from the private file printed by the launcher. Consent and click the manual URL scan.
8. Screenshot scan needs its separate opt-in and fresh consent on every capture.
   The CNN is experimental and has low measured recall; inspect its evaluation report.

Keep the launcher running during scans. Ctrl+C stops the services; the next launch
creates a new key. A browser restart forgets the extension's saved session key.
Internet is needed to install dependencies; allow several GB of free disk space.
Model inference itself runs locally and does not fetch the visited website.

The API/dashboard bind only to loopback. The launcher creates a fresh session key,
keeps event storage off and cleans up its own processes/key when stopped with Ctrl+C.
The URL model, experimental screenshot CNN and their evaluation reports are included.
The launcher loads both models; screenshot capture still requires explicit extension consent. Spark/Kafka require their
optional runtime setup; use setup_mac.sh --full and docs/pipeline.md for those paths.

Raw Desktop data is not copied, deleted or modified. To merge code into an existing
project, use install_to_mac.sh preview first. It protects data, models, environments,
Git history, .env and runtime reports. Do not unzip over your existing dataset tree.

BUILD_REPORT.md records actual executed checks and remaining acceptance boundaries.
"""
    manifest = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(contents.items())
    )
    contents["BUNDLE_MANIFEST.sha256"] = manifest.encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo(source.name + "/" + name, (2026, 11, 15, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | (0o755 if name.endswith(".sh") else 0o644)) << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip():
            raise RuntimeError("Complete bundle CRC validation failed")
        for name, data in contents.items():
            if archive.read(source.name + "/" + name) != data:
                raise RuntimeError("Complete bundle/source byte mismatch")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n")
    return {
        "files": len(contents),
        "bytes": output.stat().st_size,
        "model_version": selected.version,
        "sha256": digest,
        "raw_dataset_included": False,
        "presentation_included": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).absolute().parents[1])
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--vision-model", type=Path)
    parser.add_argument("--quality", type=Path)
    parser.add_argument("--pipeline", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            package(
                args.source,
                args.model_dir,
                args.output,
                args.quality,
                args.pipeline,
                args.vision_model,
            ),
            indent=2,
        )
    )
