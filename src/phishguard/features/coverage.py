"""Conservative review notices for URL shapes underrepresented in the supplied corpus.

This is an abstention notice, not a benign-domain allowlist or a modification of model scores.
A path or login token alone is not evidence of phishing; neither is a root URL evidence of safety.
"""

from urllib.parse import urlsplit

PATH_WARNING = (
    "Limited benign-path/login coverage in the training corpus. Legitimate login and article "
    "URLs can receive high scores. Treat this result as inconclusive and verify independently."
)


def coverage_warning(normalized_url):
    parts = urlsplit(normalized_url)
    host = parts.hostname or ""
    if parts.path not in {"", "/"} or any(
        token in host for token in ["login", "signin", "account"]
    ):
        return PATH_WARNING
    return None
