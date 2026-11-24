"""Validation-only threshold selection; test data must never be passed here."""

import numpy as np
from phishguard.ml.evaluate_models import evaluate


def select_threshold(y_validation, probabilities, max_fpr=0.05):
    if len(set(y_validation)) != 2:
        raise ValueError("Both labels required in validation split")
    candidates = []
    for threshold in np.linspace(0.05, 0.95, 91):
        report = evaluate(y_validation, probabilities, float(threshold))
        if report["false_positive_rate"] <= max_fpr:
            candidates.append(report)
    if not candidates:
        return 0.95, {"constraint_satisfied": False, "max_fpr": max_fpr}
    best = max(candidates, key=lambda r: (r["f1"], r["precision"], r["threshold"]))
    return best["threshold"], {"constraint_satisfied": True, "max_fpr": max_fpr, "validation": best}
