"""Evaluation of probabilities with explicit class polarity and undefined metric handling."""

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


def evaluate(y, probabilities, threshold=0.5):
    y = np.asarray(y, dtype=int)
    p = np.asarray(probabilities, dtype=float)
    if not len(y) or y.shape != p.shape or not np.isfinite(p).all():
        raise ValueError("Nonempty aligned finite predictions required")
    if not set(y.tolist()) <= {0, 1} or ((p < 0) | (p > 1)).any():
        raise ValueError("Binary labels and probabilities required")
    pred = p >= threshold
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    two_classes = len(np.unique(y)) == 2
    return {
        "rows": len(y),
        "threshold": threshold,
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "pr_auc": float(average_precision_score(y, p)) if two_classes else None,
        "roc_auc": float(roc_auc_score(y, p)) if two_classes else None,
        "brier": float(brier_score_loss(y, p)),
        "false_positive_rate": float(fp / (fp + tn)) if fp + tn else None,
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }
