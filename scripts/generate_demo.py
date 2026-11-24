#!/usr/bin/env python3
"""Generate explicitly synthetic .test domains. Never bundled as a trained real detector."""

import argparse
import csv
from pathlib import Path


def generate(path, domains=120):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["url", "label"])
        for i in range(domains):
            # Separate domains, mixed path lengths and mild overlap; still deliberately synthetic.
            writer.writerow([f"https://site{i}.test/" + ("about" if i % 5 else "account"), 0])
            writer.writerow([f"http://verify-{i}-account.test/login/secure/update?id={i}", 1])
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    generate(parser.parse_args().output)
