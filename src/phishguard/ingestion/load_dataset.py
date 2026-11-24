"""Streaming CSV adapter with explicit columns, label polarity and reject accounting."""

import csv
from collections import Counter
from pathlib import Path
from phishguard.features.url_features import normalize_url


class DatasetError(ValueError):
    pass


def iter_records(
    path,
    url_column="url",
    label_column="label",
    delimiter=",",
    label_map=None,
    counts=None,
    strict=False,
):
    label_map = label_map or {"0": 0, "1": 1}
    if set(label_map.values()) != {0, 1}:
        raise DatasetError("Label mapping must contain both 0=legitimate and 1=phishing")
    counts = counts if counts is not None else Counter()
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream, delimiter=delimiter)
        if not reader.fieldnames or not {url_column, label_column} <= set(reader.fieldnames):
            raise DatasetError("Explicit URL and label columns were not found")
        for row in reader:
            counts["input"] += 1
            try:
                label = label_map[row[label_column].strip()]
                url = normalize_url(row[url_column].strip())
            except (KeyError, AttributeError, ValueError, TypeError):
                counts["rejected"] += 1
                if strict:
                    raise DatasetError(f"Invalid record at CSV line {reader.line_num}") from None
                continue
            counts["accepted"] += 1
            yield {"url": url, "label": label}
