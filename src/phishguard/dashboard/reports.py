"""Read only explicitly configured minimized local reports; never browse raw datasets."""

import os
from pathlib import Path
from phishguard.common.files import read_json

REPORT_VARIABLES = {
    "model": "PHISHGUARD_EVALUATION_REPORT",
    "quality": "PHISHGUARD_DATA_QUALITY_REPORT",
    "pipeline": "PHISHGUARD_PIPELINE_REPORT",
}


def local_report(kind):
    if kind not in REPORT_VARIABLES:
        raise ValueError("Unknown dashboard report type")
    value = os.getenv(REPORT_VARIABLES[kind])
    if not value:
        return None
    return read_json(Path(value), max_bytes=5_000_000)


def performance_table(report):
    candidates = report.get("candidates", {})
    return [
        {
            "Model": name.replace("_", " ").title(),
            "Validation PR-AUC": item["validation"].get("pr_auc"),
            "Validation F1": item["validation"].get("f1"),
            "Validation false-positive rate": item["validation"].get("false_positive_rate"),
            "Eligible": item.get("selection", {}).get("constraint_satisfied", False),
        }
        for name, item in candidates.items()
    ]
