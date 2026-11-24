#!/usr/bin/env python3
"""Create an origin-only learning view; exclude every origin with contradictory labels.

No synthetic benign paths or domain allowlist. Numeric class labels are inherited, not independently verified.
"""

import argparse
import csv
import json
from pathlib import Path
from collections import Counter
from urllib.parse import urlsplit, urlunsplit
from phishguard.ingestion.load_dataset import iter_records


def curate(source, output):
    output = Path(output)
    if output.exists():
        raise ValueError("Output must be a new CSV")
    labels = {}
    counts = Counter()
    for record in iter_records(source, counts=counts):
        parts = urlsplit(record["url"])
        origin = urlunsplit((parts.scheme, parts.netloc, "/", "", ""))
        labels.setdefault(origin, set()).add(record["label"])
    conflicts = sum(len(value) > 1 for value in labels.values())
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["url", "label"])
        for origin, values in sorted(labels.items()):
            if len(values) == 1:
                writer.writerow([origin, next(iter(values))])
    return {
        "input": dict(counts),
        "unique_origins": len(labels),
        "conflicting_origins_excluded": conflicts,
        "written": len(labels) - conflicts,
        "policy": "origin-only; all ambiguous labels excluded",
        "limitations": "Inherited dataset labels and source bias remain; origin risk cannot establish individual page intent.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(curate(args.source, args.output), indent=2))
