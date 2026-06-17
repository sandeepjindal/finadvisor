"""Minimal Discord adapter: whitelist-gated message dispatch. Step 0.10.

`route_message` is a pure async function (the testable core): it enforces the whitelist
and dispatches authorized messages to a handler. `build_bot` wires it into a discord.py
client (constructed but not run in tests).
"""

from __future__ import annotations

import inspect

import discord
from bot.formatting import chunk_message
from logging_setup import get_logger
from security.guards import is_authorized

log = get_logger("bot")


async def route_message(message, allowed_ids, handler):
    """Return the handler's reply.

    - If no whitelist is configured (empty), reply with the sender's user ID so you can
      discover it for DISCORD_ALLOWED_IDS (onboarding helper).
    - Otherwise dispatch only for authorized users; ignore everyone else (returns None).
    """
    if not allowed_ids:
        return (
            f"👋 Your Discord user ID is `{message.author.id}`.\n"
            "Add it to `DISCORD_ALLOWED_IDS` in `.env` and restart, then I'll answer your "
            "questions. ⚠️ Not financial advice."
        )
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
        # Always log the sender's id so you can read it from the terminal too.
        log.info("incoming message from user_id=%s", message.author.id)
        reply = await route_message(message, cfg.discord_allowed_ids, handle_message)
        if reply:
            for chunk in chunk_message(reply):
                await message.channel.send(chunk)

    return client
