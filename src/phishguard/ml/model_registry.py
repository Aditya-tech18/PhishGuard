"""Bounded JSON logistic model format: no pickle, joblib or arbitrary-code deserialization."""

import hashlib
import json
from pathlib import Path
import numpy as np
from phishguard.features.feature_schema import FEATURE_NAMES, SCHEMA_HASH, VERSION
from phishguard.features.url_features import normalize_url, vector


class URLModel:
    def __init__(self, document):
        if document.get("format") not in {"phishguard-logistic-v1", "phishguard-classifier-v2"}:
            raise ValueError("Unsupported model format")
        if document.get("schema_hash") != SCHEMA_HASH or document.get("features") != list(
            FEATURE_NAMES
        ):
            raise ValueError("Feature schema mismatch")
        if document["format"] == "phishguard-classifier-v2":
            canonical = {key: value for key, value in document.items() if key != "version"}
            expected = hashlib.sha256(
                json.dumps(canonical, sort_keys=True, allow_nan=False).encode()
            ).hexdigest()[:16]
            if document.get("version") != expected:
                raise ValueError("Portable model content fingerprint mismatch")
        self.version = str(document["version"])
        if not 1 <= len(self.version) <= 128:
            raise ValueError("Invalid model version")
        self.threshold = float(document["threshold"])
        if not 0 < self.threshold < 1:
            raise ValueError("Invalid threshold")
        n = len(FEATURE_NAMES)
        self.mean = np.array(document["mean"], dtype=float)
        self.scale = np.array(document["scale"], dtype=float)
        from phishguard.ml.portable import PortableClassifier

        self.algorithm = document.get("algorithm", "logistic_regression")
        self.input_policy = document.get("input_policy", "full")
        if self.input_policy not in {"full", "origin-only"}:
            raise ValueError("Unsupported model input policy")
        self.query_policy = document.get("query_policy", "retain")
        if self.query_policy not in {"retain", "strip"}:
            raise ValueError("Unsupported query policy")
        params = (
            document.get("parameters")
            if document["format"] == "phishguard-classifier-v2"
            else {"weights": document["weights"], "bias": document["bias"]}
        )
        self.classifier = PortableClassifier(self.algorithm, params)
        self.weights = getattr(self.classifier, "weights", np.zeros(n))
        self.bias = getattr(self.classifier, "bias", 0.0)
        if any(
            a.shape != (n,) or not np.isfinite(a).all()
            for a in (self.mean, self.scale, self.weights)
        ):
            raise ValueError("Invalid model dimensions or non-finite weights")
        if (self.scale <= 0).any() or not np.isfinite(self.bias):
            raise ValueError("Invalid scale/bias")
        self.document = document

    @classmethod
    def load(cls, path):
        from phishguard.common.files import read_json

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(path)
        return cls(read_json(path, max_bytes=64_000_000))

    def predict(self, url):
        # Validate the original input before removing query values. urlsplit can silently
        # discard some controls, so normalization must precede privacy transformations.
        url = normalize_url(url)
        if self.query_policy == "strip":
            from urllib.parse import urlsplit, urlunsplit

            parts = urlsplit(url)
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        original = url
        if self.input_policy == "origin-only":
            from urllib.parse import urlsplit, urlunsplit

            parts = urlsplit(url)
            url = urlunsplit((parts.scheme, parts.netloc, "/", "", ""))
        x = (np.array(vector(url)) - self.mean) / self.scale
        probability, reasons = self.classifier.predict(x)
        from phishguard.features.coverage import coverage_warning

        warning = coverage_warning(original)
        return {
            "probability": probability,
            "verdict": "phishing" if probability >= self.threshold else "low_risk",
            "model_version": self.version,
            "reasons": reasons,
            "review_required": warning is not None,
            "coverage_warning": warning,
        }


def export_model(pipeline, path, threshold, metadata):
    scaler, classifier = pipeline.named_steps["scale"], pipeline.named_steps["model"]
    payload = {
        "format": "phishguard-logistic-v1",
        "feature_schema": VERSION,
        "schema_hash": SCHEMA_HASH,
        "features": list(FEATURE_NAMES),
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "weights": classifier.coef_[0].tolist(),
        "bias": float(classifier.intercept_[0]),
        "threshold": threshold,
        "metadata": metadata,
    }
    payload["version"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[
        :16
    ]
    URLModel(payload)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)
    return payload["version"]


def export_classifier(
    pipeline, path, threshold, metadata, algorithm, query_policy="strip", input_policy="full"
):
    """Export a trusted fitted pipeline into the bounded portable-v2 format."""
    from phishguard.ml.portable import export_parameters

    scaler, estimator = pipeline.named_steps["scale"], pipeline.named_steps["model"]
    payload = {
        "format": "phishguard-classifier-v2",
        "feature_schema": VERSION,
        "schema_hash": SCHEMA_HASH,
        "features": list(FEATURE_NAMES),
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "algorithm": algorithm,
        "parameters": export_parameters(estimator, algorithm),
        "threshold": float(threshold),
        "metadata": metadata,
        "query_policy": query_policy,
        "input_policy": input_policy,
    }
    payload["version"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()[:16]
    URLModel(payload)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(mode="w", dir=path.parent, prefix=".model-", delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return payload["version"]
