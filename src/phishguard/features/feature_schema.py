"""Fixed ordered schema shared by Spark, training and online inference."""

import hashlib
import json

VERSION = "lexical-v2"
FEATURE_NAMES = (
    "url_length",
    "host_length",
    "path_length",
    "query_length",
    "host_labels",
    "digit_ratio",
    "host_digit_ratio",
    "hyphens",
    "dots",
    "ats",
    "percent",
    "query_params",
    "slashes",
    "entropy",
    "host_entropy",
    "https",
    "ip_host",
    "punycode",
    "suspicious_tokens",
    "encoded_slashes",
    "port_nonstandard",
    "path_depth",
    "equals",
    "repeated_chars",
)
SCHEMA_HASH = hashlib.sha256(json.dumps(FEATURE_NAMES).encode()).hexdigest()
