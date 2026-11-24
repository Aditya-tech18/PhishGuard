"""Deterministic lexical features. Never performs DNS, HTTP, WHOIS or TLS requests."""

import ipaddress
import math
import re
from collections import Counter
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit
from phishguard.features.feature_schema import FEATURE_NAMES

TOKENS = {"login", "verify", "secure", "account", "update", "signin", "password", "wallet"}


def normalize_url(value):
    if not isinstance(value, str) or not 8 <= len(value) <= 2048:
        raise ValueError("URL must be a string of 8..2048 characters")
    if any(ord(c) < 33 or ord(c) == 127 or c.isspace() for c in value):
        raise ValueError("Whitespace and control characters are forbidden")
    if "\\" in value:
        raise ValueError("Backslashes are forbidden")
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"}:
            raise ValueError("Only HTTP(S) URLs are supported")
        if parts.username is not None or parts.password is not None:
            raise ValueError("Credentials in URLs are forbidden")
        host = parts.hostname
        if not host:
            raise ValueError("Missing hostname")
        host = host.rstrip(".").encode("idna").decode("ascii").lower()
        port = parts.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("Invalid port")
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            if not re.fullmatch(r"[a-z0-9.-]+", host) or len(host) > 253:
                raise ValueError("Invalid hostname") from None
            labels = host.split(".")
            if any(
                not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
                for label in labels
            ):
                raise ValueError("Invalid DNS label")
            if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
                raise ValueError("Local hostnames are forbidden")
            if len(labels) < 2 or re.fullmatch(r"[0-9.]+", host):
                raise ValueError("Use a public DNS hostname or canonical public IP")
        else:
            if not ip.is_global:
                raise ValueError("Non-public IP literals are forbidden")
            if ip.version == 6:
                host = f"[{ip.compressed}]"
        netloc = host + (f":{port}" if port is not None else "")
        # Query is transiently classified, never persisted by the API. Fragment isn't sent.
        normalized = urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))
        if len(normalized) > 2048:
            raise ValueError("Normalized URL exceeds the supported length")
        return normalized
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Invalid or unsupported public HTTP(S) URL") from exc


def entropy(value):
    if not value:
        return 0.0
    n = len(value)
    return -sum((count / n) * math.log2(count / n) for count in Counter(value).values())


def extract_features(url):
    url = normalize_url(url)
    parts = urlsplit(url)
    host = parts.hostname or ""
    try:
        ipaddress.ip_address(host)
        is_ip = 1.0
    except ValueError:
        is_ip = 0.0
    tokens = set(re.findall(r"[a-z]+", (host + parts.path).lower()))
    values = (
        len(url),
        len(host),
        len(parts.path),
        len(parts.query),
        len(host.split(".")),
        sum(c.isdigit() for c in url) / len(url),
        sum(c.isdigit() for c in host) / max(1, len(host)),
        url.count("-"),
        url.count("."),
        url.count("@"),
        url.count("%"),
        len(parts.query.split("&")) if parts.query else 0,
        parts.path.count("/"),
        entropy(url),
        entropy(host),
        int(parts.scheme == "https"),
        is_ip,
        int("xn--" in host),
        len(tokens & TOKENS),
        url.lower().count("%2f"),
        int(parts.port is not None and parts.port not in {80, 443}),
        len([p for p in parts.path.split("/") if p]),
        url.count("="),
        max((len(m.group(0)) for m in re.finditer(r"(.)\1+", url)), default=1),
    )
    return dict(zip(FEATURE_NAMES, map(float, values), strict=True))


def vector(url):
    values = extract_features(url)
    return [values[name] for name in FEATURE_NAMES]


@lru_cache(maxsize=1)
def _domain_extractor():
    import tldextract

    return tldextract.TLDExtract(
        suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True
    )


@lru_cache(maxsize=100000)
def domain_group(url):
    """Use bundled PSL snapshot, with network updating disabled, for leakage groups."""
    extract = _domain_extractor()
    host = urlsplit(normalize_url(url)).hostname
    parsed = extract(host)
    return parsed.top_domain_under_public_suffix or host
