import io
import logging

from logging_setup import (
    configure_logging,
    get_logger,
    REDACTED,
    register_secret,
    SecretRedactor,
)


def _logger_with_redactor(stream):
    logger = logging.getLogger("test_redaction")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.StreamHandler(stream)
    handler.addFilter(SecretRedactor())
    logger.addHandler(handler)
    return logger


def test_redaction_filter_registered_secret():
    register_secret("super-secret-token-123")
    stream = io.StringIO()
    logger = _logger_with_redactor(stream)
    logger.info("connecting with super-secret-token-123 now")
    out = stream.getvalue()
    assert "super-secret-token-123" not in out
    assert REDACTED in out


def test_redaction_filter_pattern():
    stream = io.StringIO()
    logger = _logger_with_redactor(stream)
    logger.info("auth header api_key=abcdef123456 done")
    out = stream.getvalue()
    assert "abcdef123456" not in out
    assert REDACTED in out


def test_logger_configured():
    configure_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG
    assert isinstance(get_logger("x"), logging.Logger)
