"""Domain-isolated training with validation threshold selection and held-out evaluation."""

import hashlib
import json
from pathlib import Path
from collections import Counter
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupShuffleSplit
from phishguard.features.url_features import domain_group, vector
from phishguard.ingestion.load_dataset import iter_records
from phishguard.ml.evaluate_models import evaluate
from phishguard.ml.select_model import select_threshold
from phishguard.ml.model_registry import export_model, URLModel


def split_indices(labels, groups, seed=42):
    indices = np.arange(len(labels))
    train_val, test = next(
        GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed).split(
            indices, labels, groups
        )
    )
    train, validation = next(
        GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed + 1).split(
            train_val, np.array(labels)[train_val], np.array(groups)[train_val]
        )
    )
    splits = train_val[train], train_val[validation], test
    for split in splits:
        if len(set(np.array(labels)[split])) != 2:
            raise ValueError("Each domain-isolated split needs both labels; supply more domains")
    return splits


def train(csv_path, output, report_path, seed=42, **csv_options):
    counts = Counter()
    # Exact duplicates removed; conflicting labels rejected, never resolved by majority.
    unique = {}
    for record in iter_records(csv_path, counts=counts, **csv_options):
        url, label = record["url"], record["label"]
        if url in unique and unique[url] != label:
            raise ValueError("Conflicting labels for an identical normalized URL")
        unique[url] = label
    if len(unique) < 30:
        raise ValueError("At least 30 unique valid URLs are required; demo is not real evaluation")
    urls = sorted(unique)
    labels = np.array([unique[url] for url in urls])
    groups = [domain_group(url) for url in urls]
    x = np.array([vector(url) for url in urls])
    training, validation, testing = split_indices(labels, groups, seed)
    pipeline = Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    C=1.0, max_iter=1000, class_weight="balanced", random_state=seed
                ),
            ),
        ]
    )
    pipeline.fit(x[training], labels[training])
    threshold, selection = select_threshold(
        labels[validation], pipeline.predict_proba(x[validation])[:, 1]
    )
    digest = hashlib.sha256(Path(csv_path).read_bytes()).hexdigest()
    metadata = {
        "seed": seed,
        "dataset_sha256": digest,
        "class_polarity": "1=phishing",
        "split": "registrable_domain_bundled_psl",
        "rows": len(urls),
    }
    version = export_model(pipeline, output, threshold, metadata)
    exported = URLModel.load(output)
    # Cross-check portable inference before accepting the artifact.
    p = pipeline.predict_proba(x[testing])[:, 1]
    portable = [exported.predict(urls[i])["probability"] for i in testing]
    if not np.allclose(p, portable, rtol=1e-10, atol=1e-10):
        raise RuntimeError("Export parity check failed")
    report = {
        "model_version": version,
        "input_counts": dict(counts),
        "unique_rows": len(urls),
        "split_rows": dict(
            zip(("train", "validation", "test"), map(len, (training, validation, testing)))
        ),
        "split_domains": dict(
            zip(
                ("train", "validation", "test"),
                [len({groups[i] for i in s}) for s in (training, validation, testing)],
            )
        ),
        "selection": selection,
        "test": evaluate(labels[testing], p, threshold),
        "limitations": "Dataset-dependent lexical classifier; no safety guarantee.",
    }
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    return report
