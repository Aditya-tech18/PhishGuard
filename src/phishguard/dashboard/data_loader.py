"""Dashboard calls the authenticated API server-side. No raw dataset browsing."""

import os
import httpx
from urllib.parse import urlsplit


def api(method, path, payload=None):
    base = os.getenv("PHISHGUARD_API_URL", "http://127.0.0.1:8000")
    parsed = urlsplit(base)
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Remote API requires HTTPS")
    key = os.environ["PHISHGUARD_API_KEY"]
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        response = client.request(
            method, base.rstrip("/") + path, headers={"X-API-Key": key}, json=payload
        )
        response.raise_for_status()
        return response.json()
