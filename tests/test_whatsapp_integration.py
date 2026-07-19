import hashlib
import hmac
import json
import socket
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from bot.whatsapp_bot import build_whatsapp_server


def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def whatsapp_test_ctx():
    port = get_free_port()
    cfg = SimpleNamespace(
        whatsapp_host="127.0.0.1",
        whatsapp_port=port,
        whatsapp_webhook_path="/webhook",
        whatsapp_verify_token="test_token",
        whatsapp_app_secret="test_secret",
        whatsapp_allowed_numbers=["15550100"],
        whatsapp_access_token="access_token",
        whatsapp_phone_number_id="phone_id",
        whatsapp_api_version="v20.0"
    )

    calls = []
    async def mock_handler(text):
        calls.append(text)
        return f"echo: {text}"

    with patch("bot.whatsapp_bot.httpx.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response

        server = build_whatsapp_server(cfg, mock_handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.1)

        yield cfg, server, calls, mock_client

        server.shutdown()
        server.server_close()
        thread.join()


def test_get_webhook_verification_success(whatsapp_test_ctx):
    cfg, _, _, _ = whatsapp_test_ctx
    url = f"http://127.0.0.1:{cfg.whatsapp_port}/webhook"
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "test_token",
        "hub.challenge": "challenge123"
    }
    response = httpx.get(url, params=params)
    assert response.status_code == 200
    assert response.text == "challenge123"


def test_get_webhook_verification_forbidden(whatsapp_test_ctx):
    cfg, _, _, _ = whatsapp_test_ctx
    url = f"http://127.0.0.1:{cfg.whatsapp_port}/webhook"
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong_token",
        "hub.challenge": "challenge123"
    }
    response = httpx.get(url, params=params)
    assert response.status_code == 403
    assert response.text == "forbidden"


def test_get_webhook_path_not_found(whatsapp_test_ctx):
    cfg, _, _, _ = whatsapp_test_ctx
    url = f"http://127.0.0.1:{cfg.whatsapp_port}/wrong_path"
    response = httpx.get(url)
    assert response.status_code == 404
    assert response.text == "not found"


def test_post_webhook_message_success(whatsapp_test_ctx):
    cfg, _, calls, mock_client = whatsapp_test_ctx
    url = f"http://127.0.0.1:{cfg.whatsapp_port}/webhook"

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
                                    "text": {"body": "hello test"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    body = json.dumps(payload).encode()
    signature = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()

    headers = {
        "X-Hub-Signature-256": f"sha256={signature}",
        "Content-Type": "application/json"
    }

    response = httpx.post(url, content=body, headers=headers)
    assert response.status_code == 200
    assert response.text == "ok"
    assert "hello test" in calls

    # Verify WhatsAppCloudClient was called to send the reply back
    mock_client.post.assert_called_once()
    args, kwargs = mock_client.post.call_args
    assert args[0] == f"https://graph.facebook.com/v20.0/phone_id/messages"
    assert kwargs["json"]["to"] == "15550100"
    assert kwargs["json"]["text"]["body"] == "echo: hello test"


def test_post_webhook_message_invalid_signature(whatsapp_test_ctx):
    cfg, _, _, mock_client = whatsapp_test_ctx
    url = f"http://127.0.0.1:{cfg.whatsapp_port}/webhook"

    payload = {"hello": "world"}
    body = json.dumps(payload).encode()
    headers = {
        "X-Hub-Signature-256": "sha256=invalid_signature",
        "Content-Type": "application/json"
    }

    response = httpx.post(url, content=body, headers=headers)
    assert response.status_code == 403
    assert response.text == "forbidden"
    mock_client.post.assert_not_called()


def test_post_webhook_message_non_whitelisted_ignored(whatsapp_test_ctx):
    cfg, _, _, mock_client = whatsapp_test_ctx
    url = f"http://127.0.0.1:{cfg.whatsapp_port}/webhook"

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "99999999",
                                    "id": "wamid.123",
                                    "type": "text",
                                    "text": {"body": "hello test"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    body = json.dumps(payload).encode()
    signature = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()

    headers = {
        "X-Hub-Signature-256": f"sha256={signature}",
        "Content-Type": "application/json"
    }

    response = httpx.post(url, content=body, headers=headers)
    assert response.status_code == 200
    assert response.text == "ok"
    # When whitelist is populated, unauthorized sender is silently ignored (0 posts)
    mock_client.post.assert_not_called()


def test_post_webhook_message_empty_whitelist_discovery(whatsapp_test_ctx):
    cfg, _, _, mock_client = whatsapp_test_ctx
    cfg.whatsapp_allowed_numbers = []  # Clear whitelist for discovery mode
    url = f"http://127.0.0.1:{cfg.whatsapp_port}/webhook"

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "99999999",
                                    "id": "wamid.123",
                                    "type": "text",
                                    "text": {"body": "hello test"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    body = json.dumps(payload).encode()
    signature = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()

    headers = {
        "X-Hub-Signature-256": f"sha256={signature}",
        "Content-Type": "application/json"
    }

    response = httpx.post(url, content=body, headers=headers)
    assert response.status_code == 200
    assert response.text == "ok"
    # When whitelist is empty, it returns the sender ID / setup instructions
    mock_client.post.assert_called_once()
    args, kwargs = mock_client.post.call_args
    assert "WHATSAPP_ALLOWED_NUMBERS" in kwargs["json"]["text"]["body"]
    assert "99999999" in kwargs["json"]["text"]["body"]

