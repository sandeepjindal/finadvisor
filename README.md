# Personal Financial Advisor 🤖📈

A **standalone, open-source, model-independent** AI agent that acts as your personal
financial advisor over **Discord**, **WhatsApp**, or a terminal. It reasons over live market data,
graded technicals, **multi-year fundamentals**, **analyst ratings**, **ownership/insider
activity**, news, SEC filings, macro, **geopolitical events**, and **retail/social
sentiment**; runs a full **due-diligence thesis**; remembers its own analyses in a local
"brain" and **learns from its own track record**; advises on entries, **exits**, capital
redeployment, and (educationally) day-trading and options; and proactively monitors a
portfolio you tell it about.

> ⚠️ **Advisory only — not financial advice.** This agent has **no access to bank or
> brokerage accounts** and **cannot place trades**. Markets carry risk; you can lose money.
> Always do your own research and consider a licensed advisor.

---

## ✨ Features

- **Conversational Q&A** — *"What's NVDA looking like?"* → a reasoned, **data-grounded**
  answer with cited numbers and explicit uncertainty. Handles open-ended asks too
  (*"any investment ideas?"*, *"which industries can grow?"*) proactively.
- **Full due-diligence thesis** ⭐ — *"Should I invest in MSFT?"* → `build_thesis` composes
  **valuation, multi-year financial trends, analyst ratings, ownership/insiders, growth, and
  graded price trend** into a **confirmation-required** BUY/HOLD/WATCH/SELL verdict, a
  **bear/base/bull range** (not a point forecast), and **confidence calibrated to the agent's
  own past hit-rate**.
- **Enriched trend analysis** — graded trend strength, MACD crossover, golden/death cross,
  ATR-sized stops, and **multi-timeframe** (transient-vs-structural).
- **Exit Advisor** — *"Should I sell my NVDA?"* → HOLD / TRIM / SELL, transient-vs-structural,
  ATR trailing stop, redeploy idea; **social hype-spike tightens the stop**.
- **Market/geopolitical intelligence** — *"what's moving markets?"* → detects themes
  (e.g. Middle-East conflict → energy/defense ↑, airlines/semis ↓) **confirmed against each
  sector ETF's real move**, plus an **industry outlook** ranking sectors & commodities by trend.
- **Social & search-attention signals** — StockTwits / Reddit / Google Trends; an attention
  **spike is treated as a risk flag**, never a buy signal.
- **Day-trading & options guidance** — educational, risk-first: intraday setups with
  entry/stop/target and R:R; option IV rank, break-even, probability-ITM; favors covered
  calls / cash-secured puts, warns hard on leverage.
- **Portfolio analytics, compare & discovery** — concentration/correlation/beta,
  side-by-side `compare_tickers`, and NL screening (*"cheap profitable stocks in an uptrend"*).
- **Portfolio tracking** — natural language (*"I own 30 NVDA at $450"*), `/portfolio`
  commands, or broker **CSV import**.
- **Proactive monitoring + morning digest** — daily job pings on meaningful moves
  (cooldown-deduped) and pushes a screened, macro-aware digest to Discord.
- **Learning "brain"** — a single SQLite file remembers every analysis + signal snapshot,
  scores past calls against realized price, and feeds its **track record** back into new
  advice; keyword search now, **semantic recall** planned.
- **Document ingestion** — drop PDFs/CSVs in `documents/`; the agent reads and searches them.
- **Free & model-independent** — defaults to the free [Groq](https://console.groq.com) tier;
  swap to local [Ollama](https://ollama.com) or **Claude** (Anthropic) with one env var.
  Gemini/OpenAI are stubs. No vendor lock-in.
- **Editable "skills"** — tune behavior by editing markdown in `knowledge/` and thresholds
  in `rules.yaml` — no code changes.
- **Guardrails first** — read-only tools (cannot trade), prompt-injection isolation,
  programmatic number-grounding, Discord whitelist, secret-redacted logs, SSRF protection,
  graceful degradation on rate limits / down data sources.

---

## 🧠 How it works

```
 Discord / CLI ──► Agent Engine (tool-calling loop) ──► LLM (Groq / Ollama / Claude)
              │
   ┌──────────┼───────────┬──────────────┬───────────────┬─────────────┐
   ▼          ▼           ▼              ▼               ▼             ▼
 Market    News /      Fundamentals   Events /        Social /      The "Brain"
 (yfinance) search      + analysts     geopolitics     attention     (SQLite: analyses,
  quotes/   (RSS,ddgs,  (financials,   (world news,    (StockTwits,   signal snapshots,
  trend)    SEC,FRED)   ownership,     GDELT →         Reddit,        decision outcomes,
                        valuation)     sector map)     Trends)        holdings, track record)
                          ▲
                    Scheduler (daily crawl, world scan, morning digest, monitoring)
```

The LLM is given **read-only tools** and decides which to call:
`get_quote`, `get_fundamentals`, `get_technicals`, `search_news`, `get_filings`, `get_macro`,
`assess_exit`, `recall_analysis`, `read_playbook`, document tools · **new:**
`build_thesis`, `get_analyst_ratings`, `get_ownership`, `get_financial_trends`,
`get_valuation_context`, `get_growth_estimates`, `get_catalysts`, `scan_market_context`,
`get_sector_impact`, `industry_outlook`, `get_social_signal`, `analyze_portfolio`,
`compare_tickers`, `discover_stocks`, `get_intraday`, `day_trading_plan`,
`get_options_chain`, `assess_option`, `recall_signal_history`, `assess_track_record`.
Every figure it reports is **validated against tool output** so it can't fabricate prices/ratios.

---

## 🚀 Quickstart (TL;DR)

```bash
git clone https://github.com/sandeepjindal/finadvisor
cd finadvisor
curl -LsSf https://astral.sh/uv/install.sh | sh        # install uv (mac/linux)
cp .env.example .env                                   # add GROQ_API_KEY (free)
uv sync --extra data --extra news --extra documents --extra social
uv run python scripts/chat.py                          # chat in your terminal — no Discord needed
```

---

## ✅ Prerequisites

- **Python 3.11+** and [`uv`](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- A free **Groq API key** — https://console.groq.com → API Keys. *(Or run fully local with
  [Ollama](https://ollama.com) — no key needed.)*
- **For Discord** (optional — the CLI works without it): [WIP]
  1. **https://discord.com/developers/applications** → *New Application* → **Bot** →
     *Reset Token* → copy. Enable **Message Content Intent**.
  2. **OAuth2 → URL Generator** → scope `bot` + *Send Messages* + *Read Message History* →
     open the URL → add the bot to a **private server you create** (Discord left sidebar →
     green `+` → *Create My Own*).
  3. Your **user ID**: Discord → *Settings → Advanced → Developer Mode* on, then right-click
     your name → *Copy User ID*.
- **For WhatsApp** (optional — use instead of Discord): [WIP]
  1. Create a Meta developer app, add the **WhatsApp** product, and copy the temporary or
     permanent access token plus the **Phone number ID**.
  2. Set `BOT_PLATFORM=whatsapp`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, and a
     private `WHATSAPP_VERIFY_TOKEN` in `.env`.
  3. Start the app, expose `http://localhost:8080/whatsapp/webhook` through a public HTTPS
     tunnel or deployment, then enter that callback URL and the same verify token in Meta's
     WhatsApp webhook configuration.
  4. Subscribe the webhook to `messages`, send the bot a WhatsApp message, copy the sender ID
     it replies with, add it to `WHATSAPP_ALLOWED_NUMBERS`, and restart.

---

## 🔧 Install

```bash
uv sync --extra data --extra news --extra documents
```
`uv` creates a virtualenv and installs locked dependencies. Extras are opt-in:

| Extra | Adds |
|-------|------|
| `data` | yfinance, ta, pandas, numpy (quotes, fundamentals, technicals, analysts, ownership, options, intraday) |
| `news` | feedparser, trafilatura, ddgs, vaderSentiment (news + search + sentiment + world/GDELT) |
| `documents` | pypdf (ingest PDFs) |
| `social` | pytrends, praw (Google Trends + Reddit; StockTwits needs no extra) |
| `macro` | fredapi (macro indicators) |
| `claude` | anthropic (Claude LLM provider) |
| `mcp` | mcp (optional MCP web-research backend — scaffold) |
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
| `LLM_PROVIDER` | `groq` (default) · `ollama` (local) · `claude` (Anthropic) · `gemini`/`openai` (stubs) |
| `BOT_PLATFORM` | `discord` (default) · `whatsapp` |
| `GROQ_API_KEY` / `GROQ_MODEL` | Groq credentials / model |
| `OLLAMA_MODEL` | model when `LLM_PROVIDER=ollama` |
| `ANTHROPIC_API_KEY` / `CLAUDE_MODEL` | Claude — **key optional** (falls back to an `ant auth login` profile); model defaults to `claude-opus-4-8` |
| `DISCORD_TOKEN` / `DISCORD_ALLOWED_IDS` | bot token + your whitelisted user id(s) |
| `DISCORD_DIGEST_CHANNEL_ID` | channel for the morning digest (blank = no push) |
| `WHATSAPP_VERIFY_TOKEN` | private webhook verification token you also enter in Meta |
| `WHATSAPP_ACCESS_TOKEN` / `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp Cloud API credentials for sending replies |
| `WHATSAPP_ALLOWED_NUMBERS` | comma-separated sender IDs / phone numbers allowed to use the bot |
| `WHATSAPP_APP_SECRET` | optional Meta app secret for signed webhook verification |
| `WHATSAPP_PORT` / `WHATSAPP_WEBHOOK_PATH` | local webhook listener settings; default `8080` + `/whatsapp/webhook` |
| `MARKET_TZ` / `DIGEST_TIME` | when the daily digest runs |
| `ARTICLE_RETENTION_DAYS` | prune crawled article text after N days |
| `WEB_SEARCH_BACKEND` | `ddgs` (free) / `tavily` / `mcp` |
| `MCP_SEARCH_COMMAND` / `MCP_SEARCH_URL` / `MCP_SEARCH_TOOL` | MCP research server (only if `WEB_SEARCH_BACKEND=mcp`) |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | optional Reddit app for the social signal (unauth `.json` is 403-blocked) |
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
# in .env: BOT_PLATFORM=whatsapp and fill the WHATSAPP_* values
uv run python app.py        # webhook listens on http://localhost:8080/whatsapp/webhook
```

**Docker (single container; brain + documents persist on volumes):**
```bash
docker compose up --build
```
SQLite is embedded — there is **no database container**. For 24/7 (morning digest +
monitoring), run it on an always-on host (VPS / Raspberry Pi / free-tier box).

---

## 💡 Usage

- Ask: *"What's NVDA looking like?"*, *"Compare VOO vs QQQ for ~10%/yr."*
- **Deep thesis:** *"Should I invest in MSFT?"* → full due-diligence verdict + bear/base/bull range
- **Ideas / outlook:** *"Any investment ideas?"*, *"Which industries can grow right now?"*,
  *"What's moving markets today?"*, *"Find me cheap profitable stocks in an uptrend."*
- **Exit guidance:** *"Should I sell my NVDA?"*
- **Portfolio:** *"Is my portfolio too concentrated?"* · `/portfolio add NVDA 30 450` ·
  *"I own 30 NVDA at $450"* · drop a CSV in `documents/portfolio/`
- **Higher-risk (educational):** *"Day-trade setup for TSLA?"*, *"Is the NVDA 150 call worth it?"*
- Watchlist: `/watchlist add NVDA ai leader`
- Research: drop a PDF in `documents/reports/` → *"summarize my NVDA report"*

---

## 🧪 Testing

```bash
uv run pytest -q                 # offline suite (mocked) — 398 tests
```
Full real-scenario walkthrough (live APIs + Discord/CLI, guardrail checks): see
**[`docs/TESTING.md`](docs/TESTING.md)**.

---

## 🗂️ Project structure

```
app.py · config.py · http_client.py · logging_setup.py · rules.yaml
llm/    groq · ollama · claude · factory
data/   market · news · search · technicals · macro · filings · worldnews · social ·
        analyst · ownership · financials · valuation · options · intraday · documents
brain/  db · analyses · signals (learning loop) · holdings · watchlist · cache · audit
agent/  engine · tools · thesis · exit_advisor · events · outlook · screener · daytrade ·
        options_advisor · portfolio_analytics · compare · discovery · grounding · knowledge
bot/ · scheduler/ · security/ · backtest/
knowledge/ (editable playbooks + sector_map.yaml) · documents/ (your inbox) · scripts/ · tests/
docs/plans/ (design docs) · docs/TESTING.md
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
- ✅ Market-intelligence enrichment (see `docs/plans/2026-07-15-…-design.md`):
  - **A** graded multi-timeframe trend · **B** geopolitical→sector event intelligence ·
    **C** social/attention signals · **D** learning brain + track record ·
    **E** fundamental depth + `build_thesis` · **F** day-trading & options ·
    **G** portfolio analytics / compare / discovery / industry outlook / skill playbooks.
- ✅ Claude (Anthropic) LLM provider; graceful rate-limit handling; proactive advisor prompt.
- 🔜 Phase 5C: semantic (vector) recall over the brain (designed; opt-in `[semantic]`).
- 🔜 G5: live MCP web-research backend (scaffolded + guardrailed; needs a server/key).
- 🔜 WhatsApp adapter · always-on hosting recipe.

---

## License

MIT
