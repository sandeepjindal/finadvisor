# Repository Guidelines

## Project Structure & Module Organization

This is a Python application for advisory-only financial analysis. `app.py` is the
runtime entry point; `agent/` contains orchestration and advisor logic, `data/`
contains market/news providers, `brain/` owns SQLite persistence and analysis
recall, and `llm/` contains model providers. Bot integrations live in `bot/`,
scheduled work in `scheduler/`, security controls in `security/`, and reusable
research/playbook content in `knowledge/`. Supporting imports and scripts are in
`scripts/`; documentation and plans are in `docs/`; tests mirror the feature areas
under `tests/`.

## Build, Test, and Development Commands

Use Python 3.11+ and `uv`:

```bash
uv sync --extra data --extra news --extra documents
uv run pytest -q
uv run python scripts/chat.py
uv run python app.py
docker compose up --build
```

The first command installs the locked base and selected optional dependencies.
`pytest` runs the offline suite; keep tests network-independent by mocking external
providers. `scripts/chat.py` starts terminal interaction, while `app.py` starts the
configured Discord or WhatsApp service. Docker runs the persistent service with
SQLite and mounted documents.

## Coding Style & Naming Conventions

Follow standard PEP 8 Python: four-space indentation, `snake_case` for functions,
variables, and modules, `PascalCase` for classes, and descriptive type-aware names.
Keep provider-specific code behind the existing interfaces and preserve graceful
fallbacks when optional packages or APIs are unavailable. No formatter or linter is
configured; keep changes readable and consistent with nearby code.

## Testing Guidelines

Tests use pytest with automatic asyncio support and are configured in
`pyproject.toml`. Name files `tests/test_<feature>.py` and test functions
`test_<behavior>`. Run `uv run pytest -q` before submitting changes; add focused
regression tests for new behavior, guardrails, provider fallbacks, and bot routes.

## Commit & Pull Request Guidelines

Use concise, imperative commit subjects with the project’s observed prefixes, such
as `feat(whatsapp): ...`, `test(whatsapp): ...`, `fix(...)`, or `chore(...)`.
Pull requests should explain the behavior changed, identify tests run, call out new
environment variables or optional extras, and include screenshots or example bot
transcripts when changing user-facing behavior. Never commit `.env`, API tokens,
database files, or generated personal documents.

## Security & Configuration

Copy `.env.example` to `.env` for local configuration and keep secrets out of Git.
Preserve whitelist, SSRF, prompt-injection, secret-redaction, and advisory-only
guardrails when modifying agent or integration code.
