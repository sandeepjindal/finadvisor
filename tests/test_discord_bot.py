from types import SimpleNamespace

import pytest
from bot.discord_bot import route_message


def _msg(uid, text):
    return SimpleNamespace(author=SimpleNamespace(id=uid), content=text)


@pytest.mark.asyncio
async def test_authorized_message_dispatched():
    calls = []

    def handler(text):
        calls.append(text)
        return f"echo: {text}"

    reply = await route_message(_msg(123, "hi"), {123}, handler)
    assert reply == "echo: hi"
    assert calls == ["hi"]


@pytest.mark.asyncio
async def test_unauthorized_message_ignored():
    calls = []

    def handler(text):
        calls.append(text)
        return "should not happen"

    reply = await route_message(_msg(999, "hi"), {123}, handler)
    assert reply is None
    assert calls == []


@pytest.mark.asyncio
async def test_empty_whitelist_returns_user_id_for_discovery():
    called = []

    def handler(text):
        called.append(text)
        return "should not run"

    reply = await route_message(_msg(555, "hi"), set(), handler)
    assert "555" in reply  # tells the user their id
    assert called == []  # handler not invoked in discovery mode


@pytest.mark.asyncio
async def test_async_handler_supported():
    async def handler(text):
        return f"async: {text}"

    reply = await route_message(_msg(123, "yo"), {123}, handler)
    assert reply == "async: yo"
