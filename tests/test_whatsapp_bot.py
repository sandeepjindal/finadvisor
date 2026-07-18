from types import SimpleNamespace

import pytest

from bot.whatsapp_bot import (
    extract_text_messages,
    route_message,
    verify_signature,
    verify_webhook_query,
)


def test_webhook_verification_returns_challenge_for_matching_token():
    params = {
        "hub.mode": ["subscribe"],
        "hub.verify_token": ["secret"],
        "hub.challenge": ["abc123"],
    }
    assert verify_webhook_query(params, "secret") == "abc123"


def test_webhook_verification_rejects_bad_token():
    params = {
        "hub.mode": ["subscribe"],
        "hub.verify_token": ["wrong"],
        "hub.challenge": ["abc123"],
    }
    assert verify_webhook_query(params, "secret") is None


def test_signature_is_optional_when_app_secret_missing():
    assert verify_signature(b"{}", None, None) is True


def test_signature_validation_accepts_valid_hmac():
    body = b'{"hello":"world"}'
    header = "sha256=2677ad3e7c090b2fa2c0fb13020d66d5420879b8316eb356a2d60fb9073bc778"
    assert verify_signature(body, header, "secret") is True


def test_signature_validation_rejects_invalid_hmac():
    assert verify_signature(b"{}", "sha256=bad", "secret") is False


def test_extract_text_messages_ignores_status_payloads():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"statuses": [{"id": "status"}]}}]}],
    }
    assert extract_text_messages(payload) == []


def test_extract_text_messages_returns_sender_and_text():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "15550100",
                                    "id": "wamid.123",
                                    "type": "text",
                                    "text": {"body": "What is NVDA doing?"},
                                }
                            ]
                        }
                    }
                ]
            }
        ],
    }
    messages = extract_text_messages(payload)
    assert len(messages) == 1
    assert messages[0].sender == "15550100"
    assert messages[0].text == "What is NVDA doing?"
    assert messages[0].message_id == "wamid.123"


@pytest.mark.asyncio
async def test_authorized_whatsapp_message_dispatched():
    calls = []

    def handler(text):
        calls.append(text)
        return f"echo: {text}"

    reply = await route_message("+1 555-0100", "hi", {"15550100"}, handler)
    assert reply == "echo: hi"
    assert calls == ["hi"]


@pytest.mark.asyncio
async def test_unauthorized_whatsapp_message_ignored():
    calls = []

    def handler(text):
        calls.append(text)
        return "should not happen"

    reply = await route_message("999", "hi", {"15550100"}, handler)
    assert reply is None
    assert calls == []


@pytest.mark.asyncio
async def test_empty_whatsapp_whitelist_returns_sender_id_for_discovery():
    async def handler(text):
        return SimpleNamespace(text=text)

    reply = await route_message("15550100", "hi", set(), handler)
    assert "15550100" in reply
