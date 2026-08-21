# Plan: WhatsApp Bot Integration & Verification

## Phase 1: Webhook Integration Testing [checkpoint: 3567ecb]
- [x] Task: Scaffold and write webhook integration tests
  - [x] Create mock tests in `tests/test_whatsapp_integration.py` that spin up a test `HTTPServer` on a random port.
  - [x] Implement simulated webhook GET query challenge validation checks.
  - [x] Implement simulated webhook POST request tests with valid signature, invalid signature, whitelisted number, and non-whitelisted number.
- [x] Task: Execute tests and fix webhook handler defects
  - [x] Run the new integration tests and observe any failures.
  - [x] Fix any routing or exception-handling bugs in `bot/whatsapp_bot.py` to ensure tests pass.
- [x] Task: Phase Verification & Checkpoint (Refer to workflow.md)

## Phase 2: Code Quality and Coverage Verification
- [~] Task: Verify test coverage targets
  - [ ] Run coverage analysis on `bot/whatsapp_bot.py` using `pytest --cov=bot.whatsapp_bot --cov-report=term-missing`.
  - [ ] Add unit or integration tests to cover any untested branches (e.g., error responses, exceptions during message dispatching).
  - [ ] Confirm coverage on `bot/whatsapp_bot.py` is >80%.
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)

## Phase 3: Documentation and Verification
- [ ] Task: Document manual verification setup and verify app bootstrap
  - [ ] Write step-by-step instructions for running the server locally, configuring ngrok tunneling, registering webhooks in the Meta dashboard, and checking the whitelist behavior.
  - [ ] Create walkthrough.md summarizing changes and verifying the implementation.
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)
