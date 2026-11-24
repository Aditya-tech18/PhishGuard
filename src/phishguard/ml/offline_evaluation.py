"""Evaluate an already trained artifact on a new labeled CSV without refitting it."""

from collections import Counter
from pathlib import Path
import numpy as np
from phishguard.common.files import atomic_json, read_json, sha256_file
from phishguard.features.url_features import vector, domain_group
from phishguard.ingestion.load_dataset import iter_records
from phishguard.ml.model_registry import URLModel
from phishguard.ml.evaluate_models import evaluate
from phishguard.ml.diagnostics import calibration_bins, subgroup_metrics, group_bootstrap


def evaluate_file(
    model_path, csv_path, output, reference_report=None, bootstrap=100, **csv_options
):
    model = URLModel.load(model_path)
    counts = Counter()
    records = {}
    for record in iter_records(csv_path, counts=counts, **csv_options):
        url = record["url"]
        if model.query_policy == "strip":
            from urllib.parse import urlsplit, urlunsplit

            parts = urlsplit(url)
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        if url in records and records[url] != record["label"]:
            raise ValueError("Contradictory evaluation labels after normalization")
        records[url] = record["label"]
    if not records:
        raise ValueError("No valid evaluation rows")
    urls = sorted(records)
    labels = np.asarray([records[url] for url in urls])
    probabilities = np.asarray([model.predict(url)["probability"] for url in urls])
    report = {
        "model_version": model.version,
        "algorithm": model.algorithm,
        "query_policy": model.query_policy,
        "input_counts": dict(counts),
        "dataset_sha256": sha256_file(csv_path),
        "metrics": evaluate(labels, probabilities, model.threshold),
        "calibration": calibration_bins(labels, probabilities),
        "subgroups": subgroup_metrics(labels, probabilities, urls, model.threshold),
        "limitations": "Independence from training sources must be established by the dataset owner.",
    }
    if bootstrap:
        groups = [domain_group(url) for url in urls]
        report["uncertainty"] = group_bootstrap(
            labels, probabilities, groups, model.threshold, repetitions=bootstrap
        )
    if reference_report:
        from phishguard.analytics.drift import compare_profile

        reference = read_json(reference_report)
        if reference.get("model_version") != model.version:
            raise ValueError("Reference report describes a different model")
        matrix = np.asarray([vector(url) for url in urls])
        report["input_drift"] = compare_profile(reference["training_feature_profile"], matrix)
    atomic_json(Path(output), report)
    return report
