import math
import pytest
from phishguard.features.url_features import normalize_url, extract_features, vector, domain_group
from phishguard.features.feature_schema import FEATURE_NAMES


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://localhost/",
        "http://127.0.0.1/",
        "http://[::1]/",
        "https://10.1.2.3/",
        "https://169.254.169.254/",
        "http://2130706433/",
        "https://user:password@example.com/",
        "https://example.com:99999/",
        "https://bad..com/",
        "https://example.com/\nsecret",
        "https://example.com/ a",
        "https://example.com\\@evil.com/",
        "https://-host.test/",
        "https://host.local/",
        "https://example.com:0/",
        "http://0x7f000001/",
    ],
)
def test_reject_unsupported(url):
    with pytest.raises(ValueError):
        normalize_url(url)


def test_normalization():
    assert normalize_url("HTTPS://EXAMPLE.COM#secret") == "https://example.com/"
    assert normalize_url("https://bücher.de/a?b=1") == "https://xn--bcher-kva.de/a?b=1"
    assert normalize_url("https://[2606:4700:4700::1111]/") == "https://[2606:4700:4700::1111]/"


def test_schema_and_no_io(monkeypatch):
    import socket

    monkeypatch.setattr(socket, "getaddrinfo", lambda *_: pytest.fail("DNS was attempted"))
    result = extract_features("https://example.com/login?next=foo")
    assert tuple(result) == FEATURE_NAMES
    assert all(math.isfinite(value) for value in result.values())
    assert result["https"] == 1
    assert result["suspicious_tokens"] == 1
    assert len(vector("https://example.com/")) == len(FEATURE_NAMES)


def test_domain_group_uses_psl():
    assert domain_group("https://a.shop.example.co.uk/") == "example.co.uk"
    assert domain_group("https://a.tenant.github.io/") == "tenant.github.io"


def test_idna_expansion_cannot_bypass_normalized_length_limit():
    prefix = "https://bücher.de/"
    value = prefix + "a" * (2048 - len(prefix))
    assert len(value) == 2048
    with pytest.raises(ValueError):
        normalize_url(value)
