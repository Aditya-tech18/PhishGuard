"""Offline candidate campaign clusters, never an attribution claim."""

from collections import defaultdict
from urllib.parse import urlsplit
from phishguard.features.url_features import normalize_url
import re


def candidate_campaigns(urls, minimum=3):
    groups = defaultdict(set)
    for url in urls:
        parts = urlsplit(normalize_url(url))
        template = re.sub(r"[0-9]+", "#", parts.path.lower())
        # Path-only matching intentionally produces candidates; false positives expected.
        groups[template].add(parts.hostname)
    return [
        {"path_template": key, "distinct_hosts": len(hosts), "status": "candidate"}
        for key, hosts in sorted(groups.items())
        if len(hosts) >= minimum and key != "/"
    ]
