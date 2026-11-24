"""Finite JSON model diagnostics and reproducible group-bootstrap confidence intervals."""

from collections import Counter
import numpy as np
from phishguard.ml.evaluate_models import evaluate


def calibration_bins(labels, probabilities, bins=10):
    y = np.asarray(labels, dtype=int)
    p = np.asarray(probabilities, dtype=float)
    if y.shape != p.shape or not len(y) or not np.isfinite(p).all():
        raise ValueError("Aligned finite probabilities required")
    if not set(y.tolist()) <= {0, 1} or ((p < 0) | (p > 1)).any():
        raise ValueError("Binary labels and probabilities required")
    if not 2 <= bins <= 50:
        raise ValueError("bins must be 2..50")
    assignments = np.minimum((p * bins).astype(int), bins - 1)
    rows, ece = [], 0.0
    for index in range(bins):
        selected = assignments == index
        count = int(selected.sum())
        mean = float(p[selected].mean()) if count else None
        observed = float(y[selected].mean()) if count else None
        if count:
            ece += count / len(y) * abs(mean - observed)
        rows.append(
            {
                "lower": index / bins,
                "upper": (index + 1) / bins,
                "rows": count,
                "mean_probability": mean,
                "observed_phishing_rate": observed,
            }
        )
    return {"bins": rows, "expected_calibration_error": ece}


def group_bootstrap(labels, probabilities, groups, threshold, repetitions=200, seed=42):
    """Resample whole domain groups; no row-wise confidence inflation for related URLs."""
    if not 20 <= repetitions <= 2000:
        raise ValueError("Bootstrap repetitions must be 20..2000")
    y, p, groups = np.asarray(labels), np.asarray(probabilities), np.asarray(groups)
    if not (len(y) == len(p) == len(groups)):
        raise ValueError("Aligned bootstrap arrays required")
    unique = np.unique(groups)
    if len(unique) < 5:
        raise ValueError("At least five groups required for bootstrap intervals")
    indices = {group: np.flatnonzero(groups == group) for group in unique}
    rng = np.random.default_rng(seed)
    metrics = {name: [] for name in ["precision", "recall", "f1", "pr_auc", "false_positive_rate"]}
    skipped = 0
    for _ in range(repetitions):
        sampled = rng.choice(unique, size=len(unique), replace=True)
        selected = np.concatenate([indices[group] for group in sampled])
        if len(set(y[selected])) != 2:
            skipped += 1
            continue
        report = evaluate(y[selected], p[selected], threshold)
        for name in metrics:
            metrics[name].append(report[name])
    intervals = {}
    for name, values in metrics.items():
        intervals[name] = (
            {
                "lower": float(np.quantile(values, 0.025)),
                "upper": float(np.quantile(values, 0.975)),
                "confidence": 0.95,
            }
            if values
            else None
        )
    return {
        "method": "domain_group_percentile_bootstrap",
        "seed": seed,
        "repetitions": repetitions,
        "skipped_single_class": skipped,
        "intervals": intervals,
    }


def input_profile(matrix):
    from phishguard.features.feature_schema import FEATURE_NAMES

    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != len(FEATURE_NAMES) or not len(matrix):
        raise ValueError("Expected nonempty feature matrix")
    if not np.isfinite(matrix).all():
        raise ValueError("Non-finite training features")
    return {
        name: {
            "mean": float(matrix[:, i].mean()),
            "std": float(matrix[:, i].std()),
            "p05": float(np.quantile(matrix[:, i], 0.05)),
            "p50": float(np.quantile(matrix[:, i], 0.5)),
            "p95": float(np.quantile(matrix[:, i], 0.95)),
        }
        for i, name in enumerate(FEATURE_NAMES)
    }


def subgroup_metrics(labels, probabilities, urls, threshold):
    from urllib.parse import urlsplit

    masks = {
        "https": [urlsplit(url).scheme == "https" for url in urls],
        "http": [urlsplit(url).scheme == "http" for url in urls],
        "punycode": ["xn--" in (urlsplit(url).hostname or "") for url in urls],
        "long_url": [len(url) > 200 for url in urls],
    }
    y, p = np.asarray(labels), np.asarray(probabilities)
    return {
        name: evaluate(y[np.asarray(mask)], p[np.asarray(mask)], threshold)
        for name, mask in masks.items()
        if any(mask)
    }


def class_distribution(labels):
    counts = Counter(map(int, labels))
    return {
        "legitimate": counts[0],
        "phishing": counts[1],
        "phishing_fraction": counts[1] / max(1, sum(counts.values())),
    }
