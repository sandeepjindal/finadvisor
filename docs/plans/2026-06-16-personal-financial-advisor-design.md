# Personal Financial Advisor — Design Document

**Date:** 2026-06-16
**Status:** Design validated; implemented (Phases 0–4, 174 tests passing)
**Author:** Ashish (design dialogue with Claude)

---

## 1. Purpose & Goals

Build a **standalone, open-source, platform-independent AI agent** that acts as a
**personal financial advisor**. It crawls genuine free financial information, reasons
over live market data + fundamentals + news + macro factors, remembers its own past
analyses in a local "brain," and communicates through a chat interface (Discord first).

**It is advisory-only.** It has **no access to bank/brokerage accounts** and **cannot
place trades**. Its job is to *guide* buy/hold/sell decisions and capital redeployment
with disciplined, evidence-backed reasoning.

### Top capabilities (all built)
1. **Conversational Q&A** — ask anything about a stock/fund, get a reasoned, grounded
   answer with citations and explicit caveats.
2. **Morning digest** — daily push of screened stock/fund ideas.
3. **Exit Advisor** — the differentiator: when to exit, separating *temporary dips* from
   *structural thesis breaks*.
4. **Portfolio profile + proactive monitoring** — knows what you own, monitors daily,
   pings you to lock profits / redeploy capital.
5. **Historical brain** — a local DB that remembers every analysis to inform decisions.

### Hard constraints
- **Free of cost** for ongoing personal use (free LLM tier + free data).
- **Model-independent / no Meta dependency** — pluggable LLM layer.
- **Standalone & self-hostable** — anyone can run it.
- **Secure** — it handles financial data; guardrails are first-class.

---

## 2. Architecture Overview

```
                 ┌──────────────┐
   Discord  ───► │  Bot Adapter │  (chat in/out, formatting, charts, whitelist)
                 └──────┬───────┘
                        ▼
                 ┌──────────────┐
                 │ Agent Engine │  tool-calling loop: LLM decides what data to pull
                 └──────┬───────┘
        ┌───────────────┼────────────────┬─────────────┐
        ▼               ▼                ▼             ▼
  ┌──────────┐   ┌────────────┐   ┌────────────┐  ┌─────────┐
  │ Market   │   │  News /    │   │   "Brain"  │  │  LLM    │
  │ Data     │   │  Article   │   │  (SQLite)  │  │ Layer   │
  │(yfinance,│   │(RSS+search)│   │  history + │  │pluggable│
  │ +OpenBB) │   │            │   │  analyses  │  │groq/... │
  └──────────┘   └────────────┘   └────────────┘  └─────────┘
                        ▲
                 ┌──────┴───────┐
                 │  Scheduler   │  (daily crawl, morning digest, monitoring)
                 └──────────────┘
```

**Language/runtime:** **Python 3.11+**. Every external dependency sits behind an
**interface with swappable backends** (LLM, market data, news). The **Agent Engine** is a
**tool-calling loop**: the LLM is given read-only tools and decides which to call — this is
what lets it "stretch itself" to gather what a question needs.

---

## 3. LLM Layer (pluggable, free-first)

```
LLMProvider (interface: ask, ask_with_tools, to_provider_tool_result, parse_tool_calls)
  ├─ GroqProvider     ← DEFAULT: free, fast, open models (Llama 3.3 70B / Qwen)
  ├─ OllamaProvider   ← local, private, offline (privacy mode for portfolio data)
  ├─ GeminiProvider / ClaudeProvider / OpenAIProvider ← stubs (paid, max quality)
```

Selected by one env var: `LLM_PROVIDER=groq`. Tool-calling is normalized through a
provider-neutral contract (`ToolResultMessage`/`ToolCall`) because Groq (OpenAI-style) and
Ollama differ in wire shape; Ollama also has a JSON-mode fallback for non-tool models.

**Privacy mode:** when a request involves portfolio holdings, a deterministic pre-LLM
router can send it to local Ollama so holdings never leave the machine.

---

## 4. Data Layer

### 4.1 Market data (`MarketData` facade, ordered providers, per-method fallback)
- **YFinanceProvider** — Phase-1 PRIMARY (quotes, history, fundamentals).
- **OpenBBProvider** — optional Phase-4 enrichment behind the `[openbb]` extra.
- Failures return a typed `Unavailable` marker — the engine discloses missing data, never
  fabricates. A TTL fundamentals cache (`quotes_daily`/`fundamentals` tables) softens
  free-tier rate limits.

### 4.2 News & search
- **RSSProvider** — per-ticker Yahoo headlines (scheduled daily ingest).
- **extract_article** — clean full text via `trafilatura`, guarded by SSRF check.
- **Web search** — `DDGSearch` (ddgs, default) / `TavilySearch` / `MCPSearch` (optional).
- **Sentiment** — VADER baseline; optional finBERT (`[finbert]` extra).

### 4.3 Macro / filings (Phase 4)
- **FRED** (rates, CPI, GDP, unemployment) + commodity futures via yfinance.
- **SEC EDGAR** (10-K/10-Q/8-K) — company plans, risks, guidance; descriptive User-Agent.

### 4.4 Technical indicators
- `ta` library (NumPy-2-safe — chosen over the broken `pandas-ta`): RSI, MACD, 50/200-MA,
  trend.

---

## 5. The "Brain" (local memory)

**SQLite file** — embedded, no server. Tables: `articles`, `quotes_daily`, `fundamentals`,
`analyses`, `holdings`, `watchlist`, `alerts_sent`, `audit_log`, `documents`. Indexes are
created up front; FTS5 virtual tables back keyword search (graceful LIKE fallback).

**Why `analyses` is the killer table:** every opinion is saved with *what it said, why, the
price then, and confidence*, so the agent can later detect a broken thesis. WAL mode;
POSIX file perms `600`; optional SQLCipher encryption (`[encryption]` extra).

**Storage growth:** only `articles` grows materially; a weekly maintenance job prunes old
article text past `ARTICLE_RETENTION_DAYS` and runs `VACUUM`. Reads stay sub-ms thanks to
the indexes.

---

## 6. Signal Framework

Five families: **Fundamental, Technical, Sentiment, Macro, Catalyst** — weighted by
`rules.yaml`. **Honest caveat (always surfaced):** no system predicts markets; the edge is
structured multi-factor reasoning + disciplined exits + memory, with explicit uncertainty.

---

## 7. The Exit Advisor (core differentiator)

`evaluate_exit(holding, ...)`: position math (gain %) → trend/timing (50/200-MA, RSI) →
valuation → **transient vs structural classification** → `HOLD`/`TRIM`/`SELL` + "what would
flip it" + a concrete rule (trailing stop) + a **redeploy idea**. Deterministic baseline
(testable); an LLM layer can enrich later. Output always ends with "Not financial advice."

---

## 8. Portfolio Profile + Proactive Monitoring

Holdings learned via natural language ("I own 30 NVDA at $450"), `/portfolio` commands, or
broker **CSV import** (read-only file, never credentials). A daily `monitor_holdings_job`
runs the Exit Advisor over each holding and **pushes one alert per fresh TRIM/SELL** trigger
(cooldown-deduped), pairing each exit with a redeploy idea. Needs the bot running
persistently (laptop while awake; VPS/Pi/Docker for 24/7).

---

## 9. Morning Digest + Watchlist

Scheduler triggers a morning job; the screener ranks watchlist + indices by the five-family
composite and posts a concise digest to a configured channel. `watchlist` table tracks
tickers of interest.

---

## 10. Guardrails & Security

1. **Capability restriction (hard backstop)** — no trade/payment/shell/eval/file-write
   tools exist; read-only data + own brain only. Even a hijacked LLM can't trade.
2. **Indirect prompt-injection isolation** — retrieved content wrapped in `<untrusted>`
   (with delimiter-spoof neutralization); no exfiltration tool; SSRF-safe fetch (domain
   sense + private-IP block); replies only to the owner's channel. (Capability restriction
   is the real defense; delimiters are defense-in-depth.)
3. **Number grounding** — a programmatic validator flags any figure in the answer not
   traceable to a tool-output citation.
4. **Access control** — bot responds only to whitelisted Discord user IDs.
5. **Secrets** — `.env` git-ignored; secrets registered with a logging redactor; SQLite
   perms `600`; optional encryption at rest; privacy mode → local LLM.
6. **Tool/DB safety** — parameterized SQL; input/ticker validation; HTTP timeouts + size
   caps + retry/backoff.
7. **Loop/cost controls** — max tool-iterations, per-user rate limiter, token budget.
8. **Output safety** — mandatory disclaimer; confidence + uncertainty; scope refusal.
9. **Audit trail** — every tool call + recommendation logged (secret-redacted).
10. **Backtest-before-trust** — exit rules backtested (pure-pandas) before real-money use.

---

## 11. Tooling Ecosystem (MCP + open-source)

The agent is an MCP *client* and uses custom function-tools — same loop. Core tools are
custom (reliable); external MCP reserved for web search/crawl.

| Tier | Components |
|---|---|
| **Core (custom)** | yfinance, `ta`, SEC EDGAR, FRED, trafilatura, VADER, SQLite brain |
| **High-value add-ons** | OpenBB (data backbone), ddgs/Tavily (search) |
| **Advanced/production** | vectorbt or pure-pandas backtest, finBERT, semantic recall |

---

## 11b. Agent Knowledge/Playbook Layer & Document Ingestion

**Knowledge layer (editable "skills"):** a `knowledge/` directory of markdown playbooks
(`investing_principles`, `exit_rules`, `entry_screening`, `redeploy_policy`, `glossary`,
`disclaimers`) + `rules.yaml` (signal weights, alert thresholds, cooldowns,
max-position-weight). The screener, Exit Advisor, and monitoring read `rules.yaml` →
behavior is tuned by editing config, not code. Exposed via the `read_playbook` tool.

**Document ingestion:** a local `documents/` folder (`portfolio/`, `reports/`, `notes/`).
`ingest_path` parses PDF (`pypdf`), CSV, TXT/MD → clean text → `documents` table (size-
guarded). Tools: `list_documents`, `read_document`, `search_documents`. Optional Phase-4
semantic recall over article + document text.

---

## 12. Phasing (all built)

| Phase | Delivers |
|---|---|
| **0 — Foundation** | repo, config, pluggable LLM (Groq), SQLite brain, Discord bot, logging+redaction, HTTP helper, guards |
| **1 — Q&A** | data layer, technicals, news/VADER, web search, knowledge layer, tool registry, grounding validator, agent engine, bot wiring |
| **2 — Digest + watchlist** | scheduler (tz), screener, daily crawl + digest + maintenance, `/watchlist`, rate limit |
| **3 — Portfolio + Exit + alerts** | holdings, `/portfolio` + NL + CSV, Exit Advisor, redeploy, monitoring, audit, documents |
| **4 — Production** | SEC EDGAR, macro/FRED, backtester, privacy routing, Docker/README packaging, optional OpenBB/semantic/finBERT/MCP/encryption |

---

## 13. Project Structure

```
fin-advisor/
├─ app.py, config.py, logging_setup.py, http_client.py, rules.yaml
├─ Dockerfile, docker-compose.yml, scripts/setup.sh, pyproject.toml, uv.lock
├─ llm/        base, groq_provider, ollama_provider, factory
├─ data/       market, news, search, technicals, macro, filings, csv_import,
│              documents, openbb_provider
├─ brain/      db, analyses, cache, watchlist, holdings, audit, documents, semantic
├─ agent/      engine, tools, grounding, prompts, knowledge, screener, redeploy,
│              exit_advisor, portfolio_parse, privacy
├─ bot/        discord_bot, formatting, commands
├─ scheduler/  jobs
├─ security/   guards, ratelimit
├─ backtest/   exit_rules
├─ knowledge/  *.md playbooks
├─ documents/  portfolio/ reports/ notes/ (user inbox)
└─ tests/      ~30 suites (174 tests)
```

**Dependencies (all free):** base = `discord.py`, `groq`, `ollama`, `python-dotenv`,
`httpx`, `apscheduler`, `pyyaml`; phase-scoped extras = `[data]` (yfinance, ta, pandas,
numpy), `[news]` (feedparser, trafilatura, ddgs, vaderSentiment), `[documents]` (pypdf),
`[macro]`, `[finbert]`, `[semantic]`, `[backtest]`, `[openbb]`, `[encryption]`, LLM SDKs.

---

## 14. MVP Acceptance / Demo Script (live, on a machine with internet)

1. "What's NVDA looking like?" → grounded verdict + caveat
2. "META calls right now — smart?" → reasoned, uncertainty stated
3. "Which broad index fund for ~10%/yr?" → VOO/QQQ compared
4. "I own 30 NVDA at $450, hold or sell?" → exit reasoning
5. Re-ask next run → recalls prior analysis
6. Malicious article URL (incl. spoofed `</untrusted>`) → treated as data

---

## 14b. Distribution & Standalone Packaging

Standalone with zero Meta/platform dependency; Discord is the UI (no frontend).
- **Clone + run:** `uv sync`, `uv run python app.py`.
- **Docker (recommended):** `docker compose up` — **single app container** (SQLite is
  embedded; NO db container) + optional `ollama`; brain + documents persist on volumes
  (`./.runtime:/data`, `./documents`). `restart: unless-stopped` for 24/7.
- **Cloud/always-on:** same container on a VPS / Raspberry Pi / free-tier box.
- README is the one-stop setup guide (local / Docker / cloud / config / backup).

**Data persistence:** SQLite is a single file; back up = copy `brain.db` + `documents/`.
Postgres is an optional future swap for multi-user.

---

## 15. Key Decisions (locked)

- **Language:** Python. **Chat:** Discord first (platform-agnostic core for WhatsApp later).
- **LLM:** pluggable; **Groq free tier default**; Ollama local privacy mode; paid stubs.
- **Data:** yfinance primary + OpenBB optional; RSS + ddgs search.
- **Brain:** SQLite local file. **Indicators:** `ta` (not pandas-ta).
- **Scope:** all four phases. **Hosting:** local dev; host-agnostic for 24/7.
- **Safety:** advisory-only, no broker/bank access, no trade execution — enforced by
  capability restriction.

> **Durability note (post-mortem):** the project is a *standalone* repo outside fbsource.
> Sandcastle home storage is ephemeral — it was lost once to a box recycle and rebuilt from
> the session transcript. It is now backed up via **dotsync2** (`fin-advisor` path) and has
> a **GitHub remote** (`ashuaeron/Financial-Advisor`); push from a machine with open
> internet (this devserver's proxy blocks github.com).

---

## 16. Semantic Recall (Phase 5C — detailed design)

**Problem it solves.** Today the brain retrieves by *keywords* (`search_news`/
`search_documents` via SQL `LIKE`/FTS5), which only matches exact words. Semantic recall
retrieves by *meaning*: a query like "NVIDIA data-center demand" should surface an article
titled "Hyperscaler GPU orders accelerate" even with zero word overlap. This makes the
local brain genuinely useful over time — the agent recalls *related* prior analyses, news,
and ingested PDFs by concept.

### Architecture

```
ingest (article / document / analysis)
        │  chunk_text()                 query
        ▼                                 │ embed_query()
   embed each chunk  ──►  vector store  ◄─┘
   (sentence-transformers)  (sqlite-vec in brain.db)
        │                                 │ KNN (cosine) top-k
        ▼                                 ▼
   chunks metadata table  ────────►  recall_context(query) tool → agent
```

- **Embedding model:** `sentence-transformers` `all-MiniLM-L6-v2` (384-dim, local, free,
  CPU-fine). Lazy-loaded; nothing leaves the machine (privacy-preserving).
- **Vector store:** **`sqlite-vec`** `vec0` virtual table inside the existing `brain.db`
  (no new database). **Fallback chain:** sqlite-vec → chromadb (separate dir) → disabled.
- **Chunking:** long `clean_text` is split into ~500-token chunks with small overlap; each
  chunk is embedded and stored with provenance `(kind, source_id, chunk_idx, text)`.
- **Tool:** `recall_context(query, k=5)` — registered **only when semantic is enabled**;
  article/news chunks pass through `wrap_untrusted` (documents are user-trusted).
- **Graceful degradation (C8):** `SemanticIndex.enabled` flag; if no backend, the tool is
  not registered and keyword search remains — the agent never breaks.

### Data model (added to brain.db when enabled)
```sql
-- vec0 virtual table (sqlite-vec): rowid -> 384-dim embedding
vec_chunks(embedding float[384])
-- metadata mirror keyed by the same rowid
chunks(id INTEGER PK, kind TEXT, source_id INTEGER, chunk_idx INTEGER,
       text TEXT, created_at TEXT)
```

### Keeping it in sync
`data.documents.ingest_file` and the scheduler's `daily_crawl_job` call the index when
semantic is enabled; a one-off `index_all()` backfills existing articles/documents.

### Cost & caveats (honest)
- **Heavy install:** `sentence-transformers` pulls in **PyTorch** (~hundreds of MB) — the
  largest dependency in the project; first model load is slow. Behind the `[semantic]`
  extra, opt-in only.
- **`sqlite-vec`** needs `enable_load_extension`, disabled in some Python builds → the
  fallback handles it.
- Keyword/FTS search already covers most cases; semantic is an enrichment, not a
  replacement.

### Testability
`semantic_search`/indexing accept an **injectable `embed_fn`** (default = the real model)
so unit tests exercise chunking + KNN with a tiny deterministic fake embedding (no torch).
The real-model path is covered by a `skipif`-installed smoke test.
