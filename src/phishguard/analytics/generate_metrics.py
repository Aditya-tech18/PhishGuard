"""Aggregate metadata without URLs. Predictions are not ground-truth accuracy metrics."""

from collections import Counter


def summarize(predictions):
    verdicts = Counter()
    versions = Counter()
    for item in predictions:
        verdicts[item["verdict"]] += 1
        versions[item["model_version"]] += 1
    return {
        "total": sum(verdicts.values()),
        "verdicts": dict(verdicts),
        "model_versions": dict(versions),
        "note": "Prediction distribution; not precision, recall or measured accuracy",
    }
