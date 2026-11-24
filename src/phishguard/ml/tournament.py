"""Compare five URL model families using validation only, evaluate one held-out winner.

The test set never participates in algorithm/threshold selection. Results include dataset
and split fingerprints, calibration and optional domain-bootstrap uncertainty. No raw URLs
or domain names are written into reports or model metadata.
"""

from collections import Counter
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlsplit, urlunsplit
import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from phishguard.features.url_features import vector, domain_group
from phishguard.ingestion.load_dataset import iter_records
from phishguard.ml.model_registry import URLModel, export_classifier
from phishguard.ml.train_models import split_indices
from phishguard.ml.select_model import select_threshold
from phishguard.ml.evaluate_models import evaluate
from phishguard.ml.diagnostics import (
    calibration_bins,
    input_profile,
    subgroup_metrics,
    group_bootstrap,
)


def candidates(seed=42, profile="standard"):
    from sklearn.linear_model import LogisticRegression
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.naive_bayes import GaussianNB

    if profile not in {"fast", "standard"}:
        raise ValueError("Training profile must be fast or standard")
    trees = 12 if profile == "fast" else 100
    return {
        "logistic_regression": LogisticRegression(
            max_iter=1500, class_weight="balanced", random_state=seed
        ),
        "decision_tree": DecisionTreeClassifier(
            max_depth=12, min_samples_leaf=5, class_weight="balanced", random_state=seed
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=trees,
            max_depth=12,
            min_samples_leaf=3,
            n_jobs=2,
            class_weight="balanced",
            random_state=seed,
        ),
        "gradient_boosting": GradientBoostingClassifier(
            n_estimators=trees, max_depth=3, learning_rate=0.08, random_state=seed
        ),
        "gaussian_naive_bayes": GaussianNB(var_smoothing=1e-8),
    }


def prepare(csv_path, query_policy="strip", max_rows=500_000, **csv_options):
    if query_policy not in {"strip", "retain"}:
        raise ValueError("Query policy must be strip or retain")
    counts = Counter()
    unique = {}
    for record in iter_records(csv_path, counts=counts, **csv_options):
        url = record["url"]
        if query_policy == "strip":
            parts = urlsplit(url)
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        label = record["label"]
        if url in unique and unique[url] != label:
            raise ValueError("Conflicting labels after applying query policy; curate explicitly")
        unique[url] = label
        if len(unique) > max_rows:
            raise ValueError("Training row limit exceeded; use Spark ETL and a bounded sample")
    if len(unique) < 30:
        raise ValueError("At least 30 unique valid inputs required")
    urls = sorted(unique)
    labels = np.array([unique[url] for url in urls])
    groups = np.array([domain_group(url) for url in urls])
    matrix = np.array([vector(url) for url in urls])
    return urls, labels, groups, matrix, dict(counts)


def _digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def train_tournament(
    csv_path,
    output_dir,
    seed=42,
    profile="standard",
    query_policy="strip",
    bootstrap_repetitions=200,
    max_fpr=0.05,
    input_policy="full",
    **csv_options,
):
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise ValueError("Tournament output must be a new directory")
    if input_policy not in {"full", "origin-only"}:
        raise ValueError("Unsupported model input policy")
    urls, labels, groups, x, counts = prepare(csv_path, query_policy, **csv_options)
    if input_policy == "origin-only" and any(
        urlsplit(url).path not in {"", "/"} or urlsplit(url).query for url in urls
    ):
        raise ValueError("Origin-only training requires an explicitly curated origin-only dataset")
    training, validation, testing = split_indices(labels, groups, seed)
    group_sets = [set(groups[s]) for s in (training, validation, testing)]
    if any(group_sets[a] & group_sets[b] for a, b in [(0, 1), (0, 2), (1, 2)]):
        raise RuntimeError("Domain leakage detected")
    output_dir.mkdir(parents=True, exist_ok=False)
    models, results = {}, {}
    provenance = {
        "dataset_sha256": _digest_file(csv_path),
        "seed": seed,
        "split": "registrable_domain_bundled_psl",
        "rows": len(urls),
        "query_policy": query_policy,
        "input_policy": input_policy,
        "class_polarity": "1=phishing",
    }
    for name, estimator in candidates(seed, profile).items():
        pipeline = Pipeline([("scale", StandardScaler()), ("model", estimator)])
        started = time.perf_counter()
        pipeline.fit(x[training], labels[training])
        probabilities = pipeline.predict_proba(x[validation])[:, 1]
        threshold, selection = select_threshold(labels[validation], probabilities, max_fpr=max_fpr)
        validation_report = evaluate(labels[validation], probabilities, threshold)
        model_path = output_dir / (name + ".json")
        version = export_classifier(
            pipeline, model_path, threshold, provenance, name, query_policy, input_policy
        )
        portable = URLModel.load(model_path)
        sample = validation[: min(len(validation), 512)]
        expected = pipeline.predict_proba(x[sample])[:, 1]
        actual = [portable.predict(urls[i])["probability"] for i in sample]
        if not np.allclose(expected, actual, rtol=1e-7, atol=1e-8):
            raise RuntimeError(f"Portable parity failed for {name}; no winner promoted")
        results[name] = {
            "model_version": version,
            "validation": validation_report,
            "selection": selection,
            "fit_export_seconds": time.perf_counter() - started,
            "artifact_bytes": model_path.stat().st_size,
            "portable_parity": True,
        }
        models[name] = pipeline
    eligible = [name for name in models if results[name]["selection"]["constraint_satisfied"]]
    if not eligible:
        raise ValueError(
            "No candidate met the validation false-positive constraint; no winner promoted"
        )
    # Fixed tie-breaks ensure deterministic selection without looking at held-out labels.
    winner = max(
        eligible,
        key=lambda name: (
            results[name]["validation"]["pr_auc"],
            results[name]["validation"]["f1"],
            -results[name]["artifact_bytes"],
            name,
        ),
    )
    threshold = results[winner]["validation"]["threshold"]
    p_test = models[winner].predict_proba(x[testing])[:, 1]
    champion = output_dir / "url-model.json"
    champion.write_bytes((output_dir / (winner + ".json")).read_bytes())
    report = {
        "winner": winner,
        "model_version": results[winner]["model_version"],
        "selection_metric": "validation_pr_auc_subject_to_fpr_constraint",
        "candidates": results,
        "provenance": provenance,
        "input_counts": counts,
        "unique_rows": len(urls),
        "split_rows": dict(
            zip(["train", "validation", "test"], map(len, [training, validation, testing]))
        ),
        "split_domains": dict(zip(["train", "validation", "test"], map(len, group_sets))),
        "split_fingerprints": {
            name: hashlib.sha256("\n".join(sorted(group_sets[i])).encode()).hexdigest()
            for i, name in enumerate(["train", "validation", "test"])
        },
        "test": evaluate(labels[testing], p_test, threshold),
        "calibration": calibration_bins(labels[testing], p_test),
        "subgroups": subgroup_metrics(
            labels[testing], p_test, [urls[i] for i in testing], threshold
        ),
        "training_feature_profile": input_profile(x[training]),
        "limitations": "Dataset-specific benchmark. No independent temporal/source holdout or safety guarantee.",
    }
    if bootstrap_repetitions:
        report["uncertainty"] = group_bootstrap(
            labels[testing],
            p_test,
            groups[testing],
            threshold,
            repetitions=bootstrap_repetitions,
            seed=seed,
        )
    (output_dir / "evaluation.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n"
    )
    return report
