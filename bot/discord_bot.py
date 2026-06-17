"""Minimal Discord adapter: whitelist-gated message dispatch. Step 0.10.

`route_message` is a pure async function (the testable core): it enforces the whitelist
and dispatches authorized messages to a handler. `build_bot` wires it into a discord.py
client (constructed but not run in tests).
"""

from __future__ import annotations

import inspect

import discord
from bot.formatting import chunk_message
from security.guards import is_authorized


async def route_message(message, allowed_ids, handler):
    """Return the handler's reply for authorized users, else None (silently ignored)."""
    if not is_authorized(message.author.id, allowed_ids):
        return None
    result = handler(message.content)
    if inspect.isawaitable(result):
        result = await result
    return result


def build_bot(cfg, handle_message):
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_message(message):  # pragma: no cover - exercised via live E2E
        if message.author == client.user:
            return
        reply = await route_message(message, cfg.discord_allowed_ids, handle_message)
        if reply:
            for chunk in chunk_message(reply):
                await message.channel.send(chunk)

    return client
