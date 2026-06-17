# Personal Financial Advisor 🤖📈

A **standalone, open-source, model-independent** AI agent that acts as a personal
financial advisor over Discord. It reasons over live market data, fundamentals, news,
and macro factors; remembers its own analyses in a local "brain"; advises on entries,
**exits**, and capital redeployment; and proactively monitors a portfolio you tell it
about.

> ⚠️ **Advisory only.** This agent has **no access to bank/brokerage accounts** and
> **cannot place trades**. Nothing it says is financial advice — markets carry risk.

## Highlights

- **Conversational Q&A** — ask anything about a stock or fund, get a reasoned,
  data-grounded answer with citations and explicit uncertainty.
- **Exit Advisor** — separates *temporary dips* from *structural thesis breaks* and
  tells you when to trim/sell and where to redeploy.
- **Proactive monitoring** — knows your holdings, watches them daily, and pings you on
  meaningful moves (no spam).
- **Local "brain"** — a single SQLite file remembers every analysis to inform future
  buy/sell decisions.
- **Free & model-independent** — defaults to the free [Groq](https://console.groq.com)
  tier (open models); swap to local [Ollama](https://ollama.com), Gemini, Claude, or
  OpenAI with one env var. No Meta or vendor lock-in.
- **Editable "skills"** — tune behavior by editing markdown playbooks in `knowledge/`
  and thresholds in `rules.yaml` — no code changes.

## Prerequisites

- **Python 3.11+** and [`uv`](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- A free **Groq API key** — https://console.groq.com (or use local Ollama, see below)
- A **Discord bot token** + your Discord **user ID**:
  1. https://discord.com/developers/applications → *New Application* → **Bot** → copy token; enable **Message Content Intent**.
  2. **OAuth2 → URL Generator** → scope `bot` + Send/Read Messages → open URL → add the bot to a private server you create (left sidebar → `+`).
  3. Your user ID: Discord → Settings → Advanced → **Developer Mode**, then right-click yourself → **Copy User ID**.

## Setup — local

```bash
git clone <your-repo-url> fin-advisor && cd fin-advisor
./scripts/setup.sh                         # creates .env from template
#   edit .env: DISCORD_TOKEN, DISCORD_ALLOWED_IDS, GROQ_API_KEY
uv sync --extra data --extra news --extra documents
uv run python app.py                       # then DM your bot
```

## Setup — Docker (recommended for always-on)

```bash
cp .env.example .env   # fill in keys
docker compose up --build
```
SQLite is **embedded** — there is no database container. The brain (`brain.db`) and your
`documents/` persist on host-mounted volumes (`./.runtime`, `./documents`).

## Cloud / 24/7 monitoring

For the morning digest and proactive exit alerts to fire while you're away, run it on an
always-on host — a cheap VPS, a Raspberry Pi, or any free-tier box:

```bash
git clone <repo> && cd fin-advisor && cp .env.example .env   # fill keys
docker compose up -d --build                                  # restart: unless-stopped
```

## Configuration

All config is via `.env` (see `.env.example`). Key knobs:

| Var | Purpose |
|-----|---------|
| `LLM_PROVIDER` | `groq` (free, default) · `ollama` (local/private) · `gemini`/`claude`/`openai` |
| `GROQ_API_KEY` / `GROQ_MODEL` | Groq credentials/model |
| `DISCORD_TOKEN` / `DISCORD_ALLOWED_IDS` | bot token + your whitelisted user id(s) |
| `DISCORD_DIGEST_CHANNEL_ID` | channel for the morning digest |
| `MARKET_TZ` / `DIGEST_TIME` | when the daily digest runs |
| `ARTICLE_RETENTION_DAYS` | prune crawled article text after N days |
| `WEB_SEARCH_BACKEND` | `ddgs` (free) or `tavily` |
| `PRIVACY_MODE` | `local` routes portfolio questions to Ollama |

**Switch model** = change one line: `LLM_PROVIDER=ollama`. **Tune behavior** = edit the
markdown in `knowledge/` and thresholds in `rules.yaml` — no code changes.

### Optional feature extras (install only what you need)
`uv sync --extra macro` (FRED) · `--extra finbert` (finance sentiment) ·
`--extra semantic` (vector recall) · `--extra backtest` · `--extra openbb` · `--extra encryption`

## Usage

- Ask anything: *"What's NVDA looking like?"*, *"Which index fund for ~10%/yr?"*
- Track holdings: `/portfolio add NVDA 30 450` or *"I own 30 NVDA at $450"*; drop a broker CSV into `documents/portfolio/`
- Exit guidance: *"I have 30 NVDA, hold or sell?"*
- Watchlist: `/watchlist add NVDA ai leader`
- Drop research PDFs into `documents/reports/` — the agent can read/search them

## Data & backup

Everything lives in `brain.db` + `documents/`. Back up = copy those. Delete `brain.db` to reset.

## Design & plan

See [`docs/plans/`](docs/plans/):
- `2026-06-16-personal-financial-advisor-design.md` — full architecture & decisions
- `2026-06-16-personal-financial-advisor-implementation-plan-v2.md` — build plan

## License

MIT
