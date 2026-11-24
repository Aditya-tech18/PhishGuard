"""Inspect headers and aggregate counts without printing potentially sensitive rows."""

import csv
from collections import Counter
from pathlib import Path
from phishguard.ingestion.load_dataset import iter_records


def inspect(path, **kwargs):
    counts = Counter()
    labels = Counter()
    hosts = set()
    from urllib.parse import urlsplit

    for record in iter_records(path, counts=counts, **kwargs):
        labels[str(record["label"])] += 1
        hosts.add(urlsplit(record["url"]).hostname)
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        columns = next(csv.reader(stream, delimiter=kwargs.get("delimiter", ",")), [])
    return {
        "columns": columns,
        "counts": dict(counts),
        "labels": dict(labels),
        "distinct_hosts": len(hosts),
    }
