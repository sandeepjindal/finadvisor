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
async def test_async_handler_supported():
    async def handler(text):
        return f"async: {text}"

    reply = await route_message(_msg(123, "yo"), {123}, handler)
    assert reply == "async: yo"
