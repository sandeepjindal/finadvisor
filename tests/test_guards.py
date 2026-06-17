import pytest
from security.guards import (
    is_authorized,
    is_safe_url,
    sanitize_user_text,
    validate_ticker,
)


def test_is_authorized():
    assert is_authorized(123, {123, 456})
    assert not is_authorized(999, {123, 456})


def test_validate_ticker_ok():
    assert validate_ticker("nvda") == "NVDA"
    assert validate_ticker("brk.b") == "BRK.B"


@pytest.mark.parametrize("bad", ["", "12345", "TOOLONGX", "ab cd", "$NV"])
def test_validate_ticker_rejects(bad):
    with pytest.raises(ValueError):
        validate_ticker(bad)


def test_is_safe_url_blocks_ssrf():
    assert not is_safe_url("http://169.254.169.254/latest/meta-data")  # link-local
    assert not is_safe_url("http://localhost:8080")
    assert not is_safe_url("http://127.0.0.1")
    assert not is_safe_url("http://10.0.0.5")
    assert not is_safe_url("ftp://example.com")


def test_is_safe_url_allows_public_literal_ip():
    assert is_safe_url("https://8.8.8.8/path")


def test_is_safe_url_allowlist():
    assert is_safe_url("https://8.8.8.8", allowed_domains=["example.com"]) is False


def test_sanitize_user_text():
    assert sanitize_user_text("  hi  ") == "hi"
    assert len(sanitize_user_text("x" * 9000)) == 4000
