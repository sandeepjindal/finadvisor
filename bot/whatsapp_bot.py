"""WhatsApp Cloud API adapter.

This module is intentionally thin, like the Discord adapter: it validates Meta webhook
requests, gates senders through a whitelist, dispatches text to the shared agent handler,
and sends the reply back through the WhatsApp Cloud API.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from bot.formatting import chunk_message
from logging_setup import get_logger

log = get_logger("whatsapp")

WHATSAPP_LIMIT = 4000


@dataclass(frozen=True)
class InboundText:
    sender: str
    text: str
    message_id: str | None = None


def normalize_identity(raw: str) -> str:
    return raw.strip().removeprefix("+").replace(" ", "").replace("-", "")


def verify_webhook_query(params: dict[str, list[str]], verify_token: str) -> str | None:
    """Return Meta's challenge when the webhook verification request is valid."""
    mode = (params.get("hub.mode") or [""])[0]
    token = (params.get("hub.verify_token") or [""])[0]
    challenge = (params.get("hub.challenge") or [""])[0]
    if mode == "subscribe" and token == verify_token and challenge:
        return challenge
    return None


def verify_signature(body: bytes, signature_header: str | None, app_secret: str | None) -> bool:
    """Validate X-Hub-Signature-256 when an app secret is configured."""
    if not app_secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


def extract_text_messages(payload: dict[str, Any]) -> list[InboundText]:
    """Pull inbound user text messages out of a WhatsApp webhook payload."""
    messages: list[InboundText] = []
    if payload.get("object") != "whatsapp_business_account":
        return messages

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            for msg in value.get("messages", []):
                sender = msg.get("from")
                text = (msg.get("text") or {}).get("body")
                if sender and text and msg.get("type") == "text":
                    messages.append(
                        InboundText(
                            sender=str(sender),
                            text=str(text),
                            message_id=msg.get("id"),
                        )
                    )
    return messages


async def route_message(sender: str, text: str, allowed_numbers, handler):
    """Return the handler's reply for authorized WhatsApp senders."""
    sender_id = normalize_identity(sender)
    allowed = {normalize_identity(str(item)) for item in allowed_numbers}
    if not allowed:
        return (
            f"Your WhatsApp sender ID is `{sender}`.\n"
            "Add it to `WHATSAPP_ALLOWED_NUMBERS` in `.env` and restart, then I'll "
            "answer your questions. Advisory only; not financial advice."
        )
    if sender_id not in allowed:
        return None
    result = handler(text)
    if inspect.isawaitable(result):
        result = await result
    return result


class WhatsAppCloudClient:
    def __init__(self, access_token: str, phone_number_id: str, api_version: str) -> None:
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.api_version = api_version

    @property
    def endpoint(self) -> str:
        return (
            f"https://graph.facebook.com/{self.api_version}/"
            f"{self.phone_number_id}/messages"
        )

    def send_text(self, to: str, text: str) -> None:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        for chunk in chunk_message(text, WHATSAPP_LIMIT):
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"preview_url": False, "body": chunk},
            }
            with httpx.Client(timeout=20) as client:
                response = client.post(self.endpoint, headers=headers, json=payload)
                response.raise_for_status()


def _handler_class(cfg, handle_message):
    client = WhatsAppCloudClient(
        cfg.whatsapp_access_token,
        cfg.whatsapp_phone_number_id,
        cfg.whatsapp_api_version,
    )
    webhook_path = cfg.whatsapp_webhook_path

    class WhatsAppWebhookHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # noqa: A002 - stdlib API name
            log.info("%s - %s", self.address_string(), fmt % args)

        def _send(self, status: int, body: str, content_type: str = "text/plain") -> None:
            encoded = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):  # noqa: N802 - stdlib API name
            parsed = urlparse(self.path)
            if parsed.path != webhook_path:
                self._send(404, "not found")
                return
            challenge = verify_webhook_query(
                parse_qs(parsed.query), cfg.whatsapp_verify_token
            )
            if challenge is None:
                self._send(403, "forbidden")
                return
            self._send(200, challenge)

        def do_POST(self):  # noqa: N802 - stdlib API name
            parsed = urlparse(self.path)
            if parsed.path != webhook_path:
                self._send(404, "not found")
                return

            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            if not verify_signature(
                body,
                self.headers.get("X-Hub-Signature-256"),
                cfg.whatsapp_app_secret,
            ):
                self._send(403, "forbidden")
                return

            try:
                payload = json.loads(body.decode() or "{}")
            except json.JSONDecodeError:
                self._send(400, "invalid json")
                return

            for inbound in extract_text_messages(payload):
                log.info("incoming whatsapp message from sender_id=%s", inbound.sender)
                try:
                    reply = asyncio.run(
                        route_message(
                            inbound.sender,
                            inbound.text,
                            cfg.whatsapp_allowed_numbers,
                            handle_message,
                        )
                    )
                    if reply:
                        client.send_text(inbound.sender, reply)
                except Exception as e:  # noqa: BLE001 - keep webhook alive
                    log.exception("whatsapp message handling failed: %s", e)

            self._send(200, "ok")

    return WhatsAppWebhookHandler


def build_whatsapp_server(cfg, handle_message):
    server = HTTPServer(
        (cfg.whatsapp_host, cfg.whatsapp_port),
        _handler_class(cfg, handle_message),
    )
    log.info(
        "whatsapp webhook listening on http://%s:%s%s",
        cfg.whatsapp_host,
        cfg.whatsapp_port,
        cfg.whatsapp_webhook_path,
    )
    return server
