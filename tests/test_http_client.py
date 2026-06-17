import httpx
import pytest
from http_client import get_json, get_text, HttpError


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_retry_on_5xx_then_success():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json={"ok": True})

    out = get_json(
        "https://example.test/data",
        client=_client(handler),
        sleep=lambda _: None,
    )
    assert out == {"ok": True}
    assert calls["n"] == 3


def test_timeout_propagates_as_httperror():
    def handler(request):
        raise httpx.TimeoutException("slow", request=request)

    with pytest.raises(HttpError):
        get_text(
            "https://example.test/slow",
            client=_client(handler),
            retries=2,
            sleep=lambda _: None,
        )


def test_size_cap_enforced():
    def handler(request):
        return httpx.Response(200, text="x" * 100)

    with pytest.raises(HttpError):
        get_text(
            "https://example.test/big",
            client=_client(handler),
            max_bytes=10,
            sleep=lambda _: None,
        )


def test_user_agent_present():
    seen = {}

    def handler(request):
        seen["ua"] = request.headers.get("user-agent")
        return httpx.Response(200, json={})

    get_json(
        "https://example.test/ua",
        client=_client(handler),
        user_agent="custom-agent/9.9",
        sleep=lambda _: None,
    )
    assert seen["ua"] == "custom-agent/9.9"
