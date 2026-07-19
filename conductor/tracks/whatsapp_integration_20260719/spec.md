# Specification: WhatsApp Bot Integration & Verification

## Overview
This track completes and verifies the integration of the WhatsApp Cloud API bot adapter into `fin-advisor`. While the base webhook handler and client are implemented, we need to ensure full operational stability by writing integration tests that spin up the HTTPServer and simulate Meta's challenge validation (GET) and payload routing (POST), verifying signature checking, formatting, and whitelist access control.

## Functional Requirements
1. **Webhook Verification (GET)**:
   - Handle and validate Meta's subscribe requests with a verification token.
   - Respond with the provided challenge parameter when valid, or return HTTP 403 Forbidden on mismatch.
2. **Message Processing (POST)**:
   - Verify payload authenticity using `X-Hub-Signature-256` signature verification header against the configured Meta App Secret.
   - Extract inbound text messages, validate that the sender number is whitelisted (`WHATSAPP_ALLOWED_NUMBERS`), route text to the shared agent handler, and chunk replies to stay within WhatsApp's 4000-character limit.
3. **Integration Test Suite**:
   - Write integration tests that spin up the local `HTTPServer` on a random test port, send simulated GET and POST requests using `httpx`, and assert the correct status codes, responses, and message dispatching.
4. **Local Development Documentation**:
   - Provide clear documentation in the manual walkthrough on setting up local webhooks via tunnels (e.g. ngrok), configuring the Meta developer dashboard, and registering sender IDs.

## Non-Functional Requirements
- **Robustness**: The webhook listener must degrade gracefully, logging errors without crashing the server.
- **Security**: Prevent unauthorized execution by enforcing strict SHA256 signature verification and sender whitelist validation.

## Acceptance Criteria
- [ ] Mocked integration tests covering the webhook lifecycle (GET verification, signature verification, message routing, unauthorized access, and chunking) are implemented and pass.
- [ ] Integration tests achieve >80% code coverage on `bot/whatsapp_bot.py`.
- [ ] Manual verification plan includes step-by-step instructions for running the server locally, setting up a tunnel, and verifying message routing.

## Out of Scope
- Implementing direct bank/brokerage access or trade execution (retaining the advisory-only stance).
- Creating a custom dashboard/UI for managing Whitelisted numbers (managed via `.env` / `config.py`).
