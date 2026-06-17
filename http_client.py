"""Shared HTTP helper: timeouts, retry/backoff, size caps, descriptive User-Agent.

All outbound HTTP from data/news/search/filings/macro providers goes through here so we
get consistent timeouts, exponential backoff on transient failures, response-size caps,
and graceful degradation. Step 0.2b.
"""

from __future__ import annotations

import random
import time
from typing import Callable

import httpx

DEFAULT_UA = "fin-advisor/0.1 (+https://github.com/; personal financial advisor bot)"
DEFAULT_TIMEOUT = 15.0
DEFAULT_RETRIES = 3
DEFAULT_MAX_BYTES = 5_000_000  # 5 MB
_RETRY_STATUS = {429, 500, 502, 503, 504}


class HttpError(Exception):
    """Raised when a request ultimately fails (after retries) or violates a guard."""


def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    max_bytes: int = DEFAULT_MAX_BYTES,
    user_agent: str = DEFAULT_UA,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    hdrs = {"User-Agent": user_agent}
    if headers:
        hdrs.update(headers)

    owns_client = client is None
    client = client or httpx.Client(timeout=timeout)
    last_exc: Exception | None = None
    try:
        for attempt in range(retries):
            try:
                resp = client.request(method, url, headers=hdrs, params=params)
            except httpx.HTTPError as e:
                last_exc = e
            else:
                if resp.status_code in _RETRY_STATUS:
                    last_exc = HttpError(f"{resp.status_code} for {url}")
                else:
                    content = resp.content
                    if len(content) > max_bytes:
                        raise HttpError(
                            f"Response from {url} exceeds {max_bytes} bytes "
                            f"({len(content)})"
                        )
                    return resp
            # backoff before next attempt (skip after the final attempt)
            if attempt < retries - 1:
                sleep(0.2 * (2**attempt) + random.uniform(0, 0.1))
        raise HttpError(f"Request to {url} failed after {retries} attempts: {last_exc}")
    finally:
        if owns_client:
            client.close()


def get_json(url: str, **kwargs) -> dict | list:
    resp = _request("GET", url, **kwargs)
    try:
        return resp.json()
    except ValueError as e:
        raise HttpError(f"Non-JSON response from {url}") from e


def get_text(url: str, **kwargs) -> str:
    resp = _request("GET", url, **kwargs)
    return resp.text
