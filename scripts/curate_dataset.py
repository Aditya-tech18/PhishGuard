#!/usr/bin/env python3
"""Audit normalized label conflicts; optionally exclude ALL ambiguous URLs.

Never changes input. The cleaned output contains raw URLs and should remain local.
Default policy stops on conflicts. --drop-conflicts excludes every ambiguous URL;
no majority vote, label flipping or inferred polarity is performed.
"""

import argparse
from collections import Counter, defaultdict
import csv
import json
import os
from pathlib import Path
from phishguard.ingestion.load_dataset import iter_records


def curate(source, output, *, drop_conflicts=False, strip_query=False, **options):
    source, output = Path(source).resolve(strict=True), Path(output).absolute()
    if output.exists() or output.is_symlink() or output == source:
        raise ValueError("Output must be a new file")
    for parent in output.parents:
        if parent.is_symlink():
            raise ValueError("Output path contains a symlink")
    counts = Counter()
    labels = defaultdict(set)
    for record in iter_records(source, counts=counts, **options):
        url = record["url"]
        if strip_query:
            from urllib.parse import urlsplit, urlunsplit

            parts = urlsplit(url)
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        labels[url].add(record["label"])
    conflict_count = sum(len(values) > 1 for values in labels.values())
    report = {
        "input": dict(counts),
        "unique_normalized_urls": len(labels),
        "conflicting_unique_urls": conflict_count,
        "policy": "exclude_all_ambiguous" if drop_conflicts else "fail_on_conflict",
    }
    if conflict_count and not drop_conflicts:
        raise ValueError(f"{conflict_count} conflicting URLs. No output written.")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects an existing output from accidental replacement.
    descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    written = 0
    class_counts = Counter()
    with os.fdopen(descriptor, "w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["url", "label"])
        for url, values in sorted(labels.items()):
            if len(values) != 1:
                continue
            label = next(iter(values))
            writer.writerow([url, label])
            class_counts[str(label)] += 1
            written += 1
    return {**report, "written": written, "labels": dict(class_counts)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--drop-conflicts", action="store_true")
    parser.add_argument("--strip-query", action="store_true")
    parser.add_argument("--delimiter", default=",")
    parser.add_argument("--url-column", default="url")
    parser.add_argument("--label-column", default="label")
    parser.add_argument("--positive", default="1")
    parser.add_argument("--negative", default="0")
    args = parser.parse_args()
    if args.positive == args.negative:
        raise SystemExit("Positive/negative labels must differ")
    report = curate(
        args.source,
        args.output,
        drop_conflicts=args.drop_conflicts,
        strip_query=args.strip_query,
        delimiter=args.delimiter,
        url_column=args.url_column,
        label_column=args.label_column,
        label_map={args.positive: 1, args.negative: 0},
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
