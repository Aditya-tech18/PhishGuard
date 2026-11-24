"""Offline numeric drift diagnostics with no stored URLs or claims of causal failure."""

import numpy as np
from phishguard.features.feature_schema import FEATURE_NAMES


def compare_profile(reference, matrix, z_threshold=2.0):
    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != len(FEATURE_NAMES) or len(matrix) < 10:
        raise ValueError("At least ten aligned feature rows required for a drift report")
    if not np.isfinite(matrix).all() or not 0 < z_threshold <= 20:
        raise ValueError("Invalid drift inputs")
    result = {}
    for index, name in enumerate(FEATURE_NAMES):
        baseline = reference[name]
        values = matrix[:, index]
        std = float(baseline["std"])
        delta = abs(float(values.mean()) - float(baseline["mean"]))
        if not np.isfinite(std) or std < 0:
            raise ValueError("Invalid reference standard deviation")
        normalized = delta / std if std > 1e-12 else (0.0 if delta <= 1e-12 else None)
        constant_changed = std <= 1e-12 and delta > 1e-12
        tail_fraction = float(((values < baseline["p05"]) | (values > baseline["p95"])).mean())
        result[name] = {
            "mean_shift_in_reference_std": normalized,
            "constant_reference_changed": constant_changed,
            "outside_reference_p05_p95_fraction": tail_fraction,
            "flagged": constant_changed or (normalized is not None and normalized >= z_threshold),
        }
    return {
        "rows": len(matrix),
        "features": result,
        "flagged_features": [name for name, item in result.items() if item["flagged"]],
        "note": "Descriptive covariate shift only; not evidence of degraded accuracy by itself.",
    }
