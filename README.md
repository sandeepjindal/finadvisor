# Personal Financial Advisor 🤖📈

A **standalone, open-source, model-independent** AI agent that acts as your personal
financial advisor over **Discord**, **WhatsApp**, or a terminal. It reasons over live market data,
fundamentals, technicals, news, SEC filings, and macro factors; remembers its own analyses
in a local "brain"; advises on entries, **exits**, and capital redeployment; and can
proactively monitor a portfolio you tell it about.

> ⚠️ **Advisory only — not financial advice.** This agent has **no access to bank or
> brokerage accounts** and **cannot place trades**. Markets carry risk; you can lose money.
> Always do your own research and consider a licensed advisor.

---

## ✨ Features

- **Conversational Q&A** — *"What's NVDA looking like?"* → a reasoned, **data-grounded**
  answer with cited numbers and explicit uncertainty.
- **Exit Advisor** ⭐ — *"Should I sell my NVDA?"* → HOLD / TRIM / SELL, with a
  **transient-vs-structural** call, a concrete rule (trailing stop), and a **redeploy idea**
  — refined by an optional LLM layer.
- **Portfolio tracking** — natural language (*"I own 30 NVDA at $450"*), `/portfolio`
  commands, or broker **CSV import**.
- **Proactive monitoring** — daily job watches your holdings and pings you on meaningful
  moves (cooldown-deduped, no spam).
- **Morning digest** — scheduled, screened stock/fund ideas.
- **Local "brain"** — a single SQLite file remembers every analysis to inform future
  decisions; keyword search now, **semantic recall** planned.
- **Document ingestion** — drop PDFs/CSVs in `documents/`; the agent reads and searches them.
- **Free & model-independent** — defaults to the free [Groq](https://console.groq.com) tier
  (open models); swap to local [Ollama](https://ollama.com), Gemini, Claude, or OpenAI with
  one env var. No vendor lock-in.
- **Editable "skills"** — tune behavior by editing markdown in `knowledge/` and thresholds
  in `rules.yaml` — no code changes.
- **Guardrails first** — read-only tools (cannot trade), prompt-injection isolation,
  programmatic number-grounding, Discord whitelist, secret-redacted logs, SSRF protection.

---

## 🧠 How it works

```
 Discord / WhatsApp / CLI ──► Agent Engine (tool-calling loop) ──► LLM (Groq/Ollama/…)
                          │
        ┌─────────────────┼───────────────┬──────────────┐
        ▼                 ▼               ▼              ▼
   Market data       News / search     The "Brain"     Knowledge
   (yfinance,        (RSS, ddgs,       (SQLite:        (playbooks +
    +OpenBB)          SEC EDGAR, FRED)  analyses,        rules.yaml)
                                        holdings, …)
                          ▲
                    Scheduler (daily crawl, morning digest, monitoring)
```

The LLM is given **read-only tools** (`get_quote`, `get_fundamentals`, `get_technicals`,
`search_news`, `get_filings`, `get_macro`, `assess_exit`, `recall_analysis`,
`read_playbook`, document tools) and decides which to call. Every figure it reports is
**validated against tool output** so it can't fabricate prices/ratios.

---

## 🚀 Quickstart (TL;DR)

```bash
git clone https://github.com/ashuaeronmeta/Financial-Advisor.git fin-advisor
cd fin-advisor
curl -LsSf https://astral.sh/uv/install.sh | sh        # install uv (mac/linux)
cp .env.example .env                                   # add GROQ_API_KEY (free)
uv sync --extra data --extra news --extra documents
uv run python scripts/chat.py                          # chat in your terminal — no Discord needed
```

---

## ✅ Prerequisites

- **Python 3.11+** and [`uv`](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- A free **Groq API key** — https://console.groq.com → API Keys. *(Or run fully local with
  [Ollama](https://ollama.com) — no key needed.)*
- **For Discord** (optional — the CLI works without it):
  1. **https://discord.com/developers/applications** → *New Application* → **Bot** →
     *Reset Token* → copy. Enable **Message Content Intent**.
  2. **OAuth2 → URL Generator** → scope `bot` + *Send Messages* + *Read Message History* →
     open the URL → add the bot to a **private server you create** (Discord left sidebar →
     green `+` → *Create My Own*).
  3. Your **user ID**: Discord → *Settings → Advanced → Developer Mode* on, then right-click
     your name → *Copy User ID*.
- **For WhatsApp** (optional): use the official WhatsApp Cloud API with a WhatsApp Business
  Platform test/business number. You can chat with that bot number from WhatsApp on your
  iPhone, but the official API does **not** automate your personal iPhone WhatsApp account.

---

## 🔧 Install

```bash
uv sync --extra data --extra news --extra documents
```
`uv` creates a virtualenv and installs locked dependencies. Extras are opt-in:

| Extra | Adds |
|-------|------|
| `data` | yfinance, ta, pandas, numpy (quotes, fundamentals, technicals) |
| `news` | feedparser, trafilatura, ddgs, vaderSentiment (news + search + sentiment) |
| `documents` | pypdf (ingest PDFs) |
| `macro` | fredapi (macro indicators) |
| `finbert` | transformers + torch (finance sentiment) |
| `semantic` | sentence-transformers + sqlite-vec (semantic recall — planned) |
| `backtest` | vectorbt (or pure-pandas fallback, built-in) |
| `openbb` | OpenBB enrichment provider |
| `encryption` | pysqlcipher3 (encrypted brain) |

---

## ⚙️ Configuration

Copy `.env.example` → `.env` and fill in. Key settings:

| Var | Purpose |
|-----|---------|
| `LLM_PROVIDER` | `groq` (default) · `ollama` (local) · `gemini`/`claude`/`openai` |
| `GROQ_API_KEY` / `GROQ_MODEL` | Groq credentials / model |
| `OLLAMA_MODEL` | model when `LLM_PROVIDER=ollama` |
| `DISCORD_TOKEN` / `DISCORD_ALLOWED_IDS` | bot token + your whitelisted user id(s) |
| `DISCORD_DIGEST_CHANNEL_ID` | channel for the morning digest |
| `WHATSAPP_VERIFY_TOKEN` | webhook verification token you choose in Meta Developer settings |
| `WHATSAPP_ACCESS_TOKEN` / `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp Cloud API credentials |
| `WHATSAPP_ALLOWED_NUMBERS` | comma-separated phone allowlist, e.g. `+14155550123` |
| `WHATSAPP_WEBHOOK_PATH` / `WHATSAPP_PORT` | local webhook path/port, defaults to `/webhook/whatsapp` and `8000` |
| `MARKET_TZ` / `DIGEST_TIME` | when the daily digest runs |
| `ARTICLE_RETENTION_DAYS` | prune crawled article text after N days |
| `WEB_SEARCH_BACKEND` | `ddgs` (free) / `tavily` / `mcp` |
| `PRIVACY_MODE` | `local` routes portfolio questions to Ollama |

**Switch model** = one line (`LLM_PROVIDER=ollama`). **Tune behavior** = edit `knowledge/*.md`
+ `rules.yaml`.

---

## ▶️ Run

**Terminal chat (fastest — only needs a Groq key):**
```bash
uv run python scripts/chat.py
```

**Discord bot:**
```bash
uv run python app.py        # then DM your bot or @mention it
```

**WhatsApp bot:**
```bash
uv run python whatsapp_app.py
# in another terminal, expose it with HTTPS for Meta's webhook verification:
ngrok http 8000
```
Set the Meta webhook callback URL to `https://YOUR-NGROK-DOMAIN/webhook/whatsapp` and
use the same value for `WHATSAPP_VERIFY_TOKEN` in `.env` and the Meta dashboard. Add your
iPhone number to `WHATSAPP_ALLOWED_NUMBERS`, then send a WhatsApp message to the Meta test
or business number.

**Docker (single container; brain + documents persist on volumes):**
```bash
docker compose up --build
```
SQLite is embedded — there is **no database container**. For 24/7 (morning digest +
monitoring), run it on an always-on host (VPS / Raspberry Pi / free-tier box).

---

## 💡 Usage

- Ask: *"What's NVDA looking like?"*, *"Compare VOO vs QQQ for ~10%/yr."*
- Track: `/portfolio add NVDA 30 450` · *"I own 30 NVDA at $450"* · drop a CSV in
  `documents/portfolio/`
- **Exit guidance:** *"Should I sell my NVDA?"*
- Watchlist: `/watchlist add NVDA ai leader`
- Research: drop a PDF in `documents/reports/` → *"summarize my NVDA report"*

---

## 🧪 Testing

```bash
uv run pytest -q                 # offline suite (mocked) — 180+ tests
```
Full real-scenario walkthrough (live APIs + Discord/CLI, guardrail checks): see
**[`docs/TESTING.md`](docs/TESTING.md)**.

---

## 🗂️ Project structure

```
app.py · whatsapp_app.py · config.py · http_client.py · logging_setup.py · rules.yaml
llm/ · data/ · brain/ · agent/ · bot/ · scheduler/ · security/ · backtest/
knowledge/ (editable playbooks) · documents/ (your inbox) · scripts/ · tests/
docs/plans/ (design + implementation plan) · docs/TESTING.md
```

---

## 🔒 Security & guardrails

Capability restriction (no trade/exec tools), prompt-injection isolation
(`<untrusted>` + spoof neutralization), programmatic number-grounding, Discord whitelist,
SSRF-safe fetch, parameterized SQL, secret-redacted logs, advisory-only disclaimers,
audit log. Your `.env` is git-ignored — keys never reach the repo.

---

## 🗺️ Roadmap

- ✅ Phases 0–4: Q&A, digest, watchlist, portfolio, Exit Advisor, monitoring, documents,
  filings, macro, backtest, packaging.
- ✅ Phase 5A/B: Exit Advisor + macro wired into chat; LLM-enriched exit reasoning.
- 🔜 Phase 5C: semantic (vector) recall over the brain (design in `docs/plans/`).
- ✅ WhatsApp adapter via the official Cloud API webhook.
- 🔜 Always-on hosting recipe.

---

## License

MIT
