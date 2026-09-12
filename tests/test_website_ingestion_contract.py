import pytest

from app.knowledge.crawler import is_private_host
from app.sync.quality import normalize_http_url, valid_http_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("example.com", "https://example.com"),
        ("www.example.com", "https://www.example.com"),
        ("https://example.com/store", "https://example.com/store"),
        ("http://example.com/", "http://example.com/"),
    ],
)
def test_normalize_http_url(raw, expected):
    assert normalize_http_url(raw) == expected
    assert valid_http_url(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "javascript:alert(1)",
        "ftp://example.com",
        "https://user:password@example.com",
        "https://example.com:bad-port",
        "https:// example.com",
    ],
)
def test_normalize_http_url_rejects_invalid_values(raw):
    with pytest.raises(ValueError):
        normalize_http_url(raw)
    assert not valid_http_url(raw)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost",
        "http://127.0.0.1",
        "http://10.0.0.1",
        "http://192.168.1.1",
        "http://169.254.169.254",
    ],
)
def test_ssrf_literal_hosts_are_blocked(url):
    assert is_private_host(url) is True
