"""Input/authorization guards: Discord whitelist, ticker validation, SSRF-safe URLs,
text sanitization. Step 0.9.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

_TICKER_RE = re.compile(r"^[A-Z][A-Z.\-]{0,5}$")
MAX_TEXT_LEN = 4000


def is_authorized(user_id: int, allowed_ids) -> bool:
    return user_id in set(allowed_ids)


def validate_ticker(s: str) -> str:
    t = (s or "").strip().upper()
    if not _TICKER_RE.match(t):
        raise ValueError(f"Invalid ticker: {s!r}")
    return t


def _ip_is_unsafe(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def is_safe_url(url: str, allowed_domains: list[str] | None = None) -> bool:
    """True only for http(s) URLs that resolve to public IPs (SSRF protection)."""
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = p.hostname
    if not host:
        return False
    if allowed_domains is not None and not any(
        host == d or host.endswith("." + d) for d in allowed_domains
    ):
        return False

    # Literal IP?
    try:
        return not _ip_is_unsafe(ipaddress.ip_address(host))
    except ValueError:
        pass

    if host.lower() == "localhost":
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False  # cannot verify -> treat as unsafe
    for info in infos:
        try:
            if _ip_is_unsafe(ipaddress.ip_address(info[4][0])):
                return False
        except ValueError:
            return False
    return True


def sanitize_user_text(s: str, max_len: int = MAX_TEXT_LEN) -> str:
    return (s or "").strip()[:max_len]
