"""Structured logging with secret redaction.

`configure_logging()` installs a root handler whose `SecretRedactor` filter scrubs
registered secret values (and a few obvious patterns) from every log line. Config and
other modules call `register_secret()` for each loaded secret so it can never leak into
logs. Step 0.1c.
"""

from __future__ import annotations

import logging
import re

REDACTED = "***REDACTED***"

# Registered literal secrets (API keys, tokens). Populated at runtime via register_secret.
_SECRETS: set[str] = set()

# Heuristic patterns for secret-bearing key/value pairs, e.g. `api_key=abc`, `token: xyz`,
# `Authorization: Bearer abc`. Group 2 (the value) is redacted.
_PATTERNS = [
    re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password|passwd|authorization|bearer)\b"
        r"\s*[:=]?\s*([A-Za-z0-9._\-]{6,})"
    ),
]


def register_secret(value: str | None) -> None:
    """Register a secret value to be redacted from all log output."""
    if value and isinstance(value, str) and len(value) >= 4:
        _SECRETS.add(value)


def _redact(text: str) -> str:
    for secret in _SECRETS:
        if secret in text:
            text = text.replace(secret, REDACTED)
    for pat in _PATTERNS:
        text = pat.sub(lambda m: f"{m.group(1)}={REDACTED}", text)
    return text


class SecretRedactor(logging.Filter):
    """Logging filter that redacts secrets from the formatted message."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 (logging API)
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            message = str(record.msg)
        record.msg = _redact(message)
        record.args = ()
        return True


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger with a redacting handler. Idempotent."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    # Replace existing handlers so re-configuration is clean and the filter is always present.
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.addFilter(SecretRedactor())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
