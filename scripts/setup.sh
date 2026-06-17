#!/usr/bin/env bash
# First-run setup: create .env from the template and print next steps.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "✅ Created .env from template."
else
  echo "ℹ️  .env already exists; leaving it as-is."
fi

echo
echo "Next steps:"
echo "  1) Edit .env and set: DISCORD_TOKEN, DISCORD_ALLOWED_IDS, GROQ_API_KEY"
echo "  2) Local run:   uv sync --extra data --extra news --extra documents && uv run python app.py"
echo "  3) Or Docker:   docker compose up --build"
