#!/usr/bin/env python3
"""Export an allowlisted URL-only Vercel project. Never copies training data or secrets."""

import argparse
import json
import shutil
from pathlib import Path
from phishguard.ml.model_registry import URLModel
from phishguard.common.files import read_json, reject_symlink_chain


def prepare(source, model, evaluation, destination):
    source = reject_symlink_chain(source).resolve(strict=True)
    destination = Path(destination).absolute()
    if destination.exists() or source in destination.parents:
        raise ValueError("Choose a new destination outside the source project")
    model = reject_symlink_chain(model)
    selected = URLModel.load(model)
    report = read_json(evaluation)
    if report.get("model_version") != selected.version:
        raise ValueError("Selected URL model and evaluation do not match")
    templates = source / "deploy/vercel"
    files = [
        templates / name
        for name in ["app.py", "vercel.json", "requirements.txt", ".python-version"]
    ]
    files += list((templates / "public").rglob("*"))
    code = source / "src/phishguard"
    modules = ["__init__.py", "ml/__init__.py", "ml/model_registry.py", "ml/portable.py"]
    for directory in ["api", "common", "features"]:
        modules += [p.relative_to(code).as_posix() for p in (code / directory).glob("*.py")]
    # Resolve all inputs before creating a destination. Symlinks cannot smuggle extra files.
    planned = [(p, p.relative_to(templates)) for p in files if p.is_file()]
    planned += [(code / name, Path("phishguard") / name) for name in modules]
    for path, _ in planned:
        reject_symlink_chain(path)
    destination.mkdir(parents=True, mode=0o755)
    for path, relative in planned:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    (destination / "models").mkdir()
    shutil.copyfile(model, destination / "models/url-model.json")
    card = {
        "model_version": selected.version,
        "algorithm": selected.algorithm,
        "input_policy": selected.input_policy,
        "review_policy": "Non-root/login inputs require independent review; raw model scores are not altered by the review notice.",
        "threshold": selected.threshold,
        "query_policy": selected.query_policy,
        "test": {
            k: report["test"][k]
            for k in ["rows", "precision", "recall", "f1", "false_positive_rate"]
        },
        "evaluation_scope": "registrable-domain held-out split; not a guarantee on current websites",
        "training_rows": report.get("split_rows", {}).get("train"),
        "limitations": "Lexical URL features only; no destination fetching, page intent or independent source/time holdout.",
    }
    (destination / "models/model-card.json").write_text(
        json.dumps(card, indent=2, allow_nan=False) + "\n"
    )
    shutil.copyfile(source / "docs/vercel.md", destination / "README.md")
    shutil.copyfile(source / "LICENSE", destination / "LICENSE")
    (destination / ".gitignore").write_text(".vercel/\n.env*\n__pycache__/\n.venv/\n")
    (destination / ".vercelignore").write_text(".git/\n.vercel/\n.env*\n__pycache__/\n.venv/\n")
    return {
        "files": sum(p.is_file() for p in destination.rglob("*")),
        "model_version": selected.version,
        "profile": "stateless-url-only",
        "secrets_included": False,
        "raw_data_included": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.model, args.evaluation, args.output), indent=2))
