# Plan: Personal Financial Advisor — Full Implementation (All Phases) — v2

**Goal**: Ship a standalone, open-source, model-independent AI agent that advises on
stocks/funds via Discord — live data + reasoning + a persistent local "brain" + an Exit
Advisor + proactive portfolio monitoring — with strong guardrails. Advisory-only; no
broker/bank access; no trade execution.

**Status**: Implemented. All phases complete, 174 pytest tests passing. This document is
the build plan of record; the code under the package tree is now the source of truth.

**Architecture**: Python tool-calling agent. Pluggable LLM (Groq default, Ollama local,
Claude/Gemini/OpenAI stubs). Data behind interfaces (yfinance primary, OpenBB optional,
RSS + plain web-search). SQLite "brain." Discord adapter. APScheduler for daily jobs.
Capability-restricted (read-only tools only). See companion design doc
`2026-06-16-personal-financial-advisor-design.md`.

---

## Changes from v1 (review fixes — `implementation-plan-review-1.md`)

- **C1 Number grounding (programmatic):** `agent/grounding.py` validates every numeric
  token in the answer against collected tool-output `Citation`s; engine flags unsupported
  figures. Dedicated TDD step.
- **C2 pandas-ta on NumPy 2.x:** switched indicators to the **`ta`** library (NumPy-2-safe);
  added a Phase-1 import smoke test.
- **C3 Dependency pinning:** `uv` + committed `uv.lock` + **phase-scoped optional extras**
  so heavy libs (torch/openbb/vectorbt/sentence-transformers/sqlite-vec) are opt-in.
- **C4 OpenBB:** yfinance is the Phase-1 **primary**; OpenBB demoted to an optional Phase-4
  enrichment provider behind `[openbb]`.
- **C5 Web search:** plain Python (`ddgs`/Tavily) on the critical path; MCP an optional
  later adapter.
- **C6 Sentiment:** VADER baseline; finBERT optional (`[finbert]`).
- **C7 Parallelism correctness:** shared files split into distinct modules
  (`brain/analyses|holdings|watchlist|audit|cache`, `security/guards|ratelimit`,
  `agent/screener|redeploy`, `bot/commands`).
- **C8 Platform caveats:** POSIX-only chmod (test skipped on Windows); SQLCipher via
  `pysqlcipher3` optional; sqlite-vec gated with graceful disable.
- **C9 Tool-calling parity:** provider-neutral tool-result contract + parity tests for Groq
  and Ollama (incl. JSON-mode fallback).
- **C10 Injection:** capability restriction + no-exfil + owner-channel-only are the real
  defenses; `<untrusted>` wrapping with delimiter-spoof neutralization is defense-in-depth.
- **Cross-cutting:** structured logging + secret redaction; shared HTTP retry/backoff;
  Discord 2000-char chunking; scheduler timezone; explicit `.env` load order; CSV import;
  caches wired (not unused); privacy-mode deterministic router.

---

## Tech Stack

- **Runtime:** Python 3.11+ (dev interpreter here: `fbpython` 3.12).
- **Base:** `discord.py`, `groq`, `ollama`, `python-dotenv`, `httpx`, `apscheduler`,
  `pyyaml`, `pytest`, `pytest-asyncio` (dev group).
- **Extras:** `[data]` yfinance/ta/pandas/numpy · `[news]` feedparser/trafilatura/ddgs/
  vaderSentiment · `[documents]` pypdf · `[macro]` fredapi · `[finbert]` transformers/torch ·
  `[semantic]` sentence-transformers/sqlite-vec · `[backtest]` vectorbt · `[openbb]` openbb ·
  `[encryption]` pysqlcipher3 · LLM SDK extras.
- **Indicator decision:** `ta` (not `pandas-ta`, which breaks on NumPy 2.x).

---

## Conventions

- **Dependency manager:** `uv` (lockfile-first). `uv sync`; per-phase `uv sync --extra data
  --extra news`. Dev venv kept OUTSIDE the repo (`UV_PROJECT_ENVIRONMENT`) to keep git/
  dotsync clean.
- **Tests:** `pytest`; offline/mocked (no network, no keys). Modules import-safe (lazy
  clients). Live calls only in manual per-phase E2E.
- **TDD per step:** failing test → red → implement → green → commit.
- **Commits:** `git commit -m "[finadv] Step N.M: ..."` (standalone git repo).
- **Secrets:** never commit `.env`; redacted from logs.

---

## Execution Order (true parallelism)

| Group | Phase | Genuinely parallel (distinct files) | Sequential (shared file / dep) |
|---|---|---|---|
| G0 | 0 | 0.3/0.4/0.5 (llm/*), 0.7 (brain/db), 0.9 (guards), 0.10 (bot) | 0.1→0.1b→0.1c; 0.2→0.2b; 0.6 needs 0.3–0.5; 0.8 needs 0.7; 0.11 needs all |
| G1 | 1 | 1.1 (market), 1.3 (technicals), 1.4 (news), 1.5 (search) | 1.1→1.2→1.2b; 1.6→1.6b→1.7→1.8→1.9; 1.9a/b needs engine |
| G2 | 2 | 2.0 (tz), 2.1 (watchlist), 2.2 (screener), 2.5 (ratelimit) | 2.3 needs 2.2; 2.4 needs 2.1+2.3 |
| G3 | 3 | 3.1 (holdings), 3.3 (exit_advisor), 3.4 (redeploy), 3.6 (audit) | 3.2/3.2b need 3.1; 3.5 needs 3.3+2.3; 3.7 doc tools |
| G4 | 4 | 4.0 (openbb), 4.1 (filings), 4.2 (macro), 4.4 (backtest), 4.6 (privacy) | 4.5 (encryption), 4.7 (packaging), 4.x optionals |

---

## File Tree (split into independent modules — C7)

```
fin-advisor/
├─ app.py · config.py · logging_setup.py · http_client.py · rules.yaml · conftest.py
├─ Dockerfile · docker-compose.yml · scripts/setup.sh · pyproject.toml · uv.lock
├─ llm/   base.py groq_provider.py ollama_provider.py factory.py
├─ data/  market.py news.py search.py technicals.py macro.py filings.py csv_import.py
│         documents.py openbb_provider.py
├─ brain/ db.py analyses.py cache.py watchlist.py holdings.py audit.py documents.py semantic.py
├─ agent/ engine.py tools.py grounding.py prompts.py knowledge.py screener.py redeploy.py
│         exit_advisor.py portfolio_parse.py privacy.py
├─ bot/   discord_bot.py formatting.py commands.py
├─ scheduler/ jobs.py · security/ guards.py ratelimit.py · backtest/ exit_rules.py
├─ knowledge/ *.md · documents/ portfolio|reports|notes · tests/ (~30 suites)
```

---

# PHASE 0 — Foundation

- **0.1 Scaffolding** — `pyproject.toml` (base deps + empty extras), `.gitignore`,
  `.env.example`, `README.md`, `conftest.py`. → `git init`.
- **0.1b Lockfile + extras** — fill `[extras]`, `uv lock`, clean-install verification.
- **0.1c Logging + secret redaction** — `logging_setup.py`: `configure_logging`,
  `SecretRedactor`, `register_secret`, `get_logger`.
- **0.2 Config** — `config.py`: `load_config()` frozen `Config`, per-provider validation,
  registers secrets. **0.2b HTTP helper** — `http_client.py`: timeouts, retry/backoff,
  size caps, User-Agent.
- **0.3 LLM interface + contract** — `llm/base.py` dataclasses + abstract methods.
  **0.3b parity tests** — `tests/test_tool_contract.py` (Groq + Ollama).
- **0.4 Groq provider** / **0.5 Ollama provider** (lazy clients) / **0.6 factory**.
- **0.7 Brain DB schema** — `brain/db.py`: 9 tables + indexes + FTS5 + WAL + POSIX 600.
  **0.8 analyses store** (parameterized, injection-safe).
- **0.9 Security guards** — whitelist, ticker validation, SSRF-safe URLs, sanitize.
- **0.10 Discord bot** — `route_message` (pure, testable) + `build_bot`.
- **0.11 App entrypoint** — `bootstrap()` with `load_dotenv` first; call-order test.
  **Phase 0 live E2E (`#15`, needs keys/laptop):** bot replies via Groq; whitelist enforced.

# PHASE 1 — Conversational Q&A Agent

- **1.1 yfinance provider** (primary) + typed `Quote`/`Fundamentals` + `Unavailable`.
  **1.2 per-method fallback facade.** **1.2b fundamentals cache** (`brain/cache.py`).
- **1.3 Technicals** (`ta`): RSI/MACD/SMA/trend. **1.4 News** RSS + safe extract + VADER +
  import smoke test. **1.5 Web search** (ddgs/Tavily).
- **1.6 Prompts** + injection isolation + `Citation`. **1.6b Knowledge layer** —
  `knowledge/*.md` + `rules.yaml` + `agent/knowledge.py` (validated `load_rules`).
- **1.7 Tool registry** (read-only, citation-emitting; `get_quote/get_fundamentals/
  get_technicals/search_news/recall_analysis/read_playbook` + later doc/filings tools).
- **1.8 Grounding validator.** **1.9 Agent engine** (tool loop + cap + grounding + save +
  audit). **1.9a/b** wire into bot + `format_answer` + chunking.
- **Phase 1 live E2E (`#28`, needs keys/laptop):** the 6-question demo script.

# PHASE 2 — Morning Digest + Watchlist

- **2.0 Scheduler + tz** (`build_scheduler`, `parse_digest_time`). **2.1 Watchlist store.**
- **2.2 Screener** (5-family composite weighted by `rules.yaml`). **2.3 Jobs** — daily crawl
  (→ articles + FTS), digest builder/formatter, maintenance (retention prune + VACUUM).
- **2.4 `/watchlist` commands + digest delivery.** **2.5 Rate limiter + token budget.**

# PHASE 3 — Portfolio + Exit Advisor + Alerts

- **3.1 Holdings + alerts store** (cooldown/dedupe). **3.2 `/portfolio` + NL parsing.**
  **3.2b CSV import** (tolerant columns, validated).
- **3.3 Exit Advisor** (position math, trend/RSI/valuation, transient/structural,
  HOLD/TRIM/SELL + rule + redeploy + citations). **3.4 Redeploy screener.**
- **3.5 Monitoring job** (one alert per fresh TRIM/SELL, cooldown-deduped). **3.6 Audit
  logging** (secret-redacted, wired into engine). **3.7 Document ingestion** (PDF/CSV/notes
  + doc tools + startup scan).

# PHASE 4 — Production Hardening

- **4.0 OpenBB** optional enrichment provider (`[openbb]`). **4.1 SEC EDGAR filings**
  (+ tool, descriptive UA). **4.2 Macro/FRED + commodities** (injectable clients).
- **4.4 Backtest** trailing-stop (pure-pandas, vectorbt-free). **4.6 Privacy routing**
  (deterministic pre-LLM). **4.7 Packaging** — Dockerfile + compose (single container,
  /data volume) + setup.sh + full README.
- **4.x Optional guarded modules:** semantic recall (sqlite-vec/chromadb fallback), finBERT
  sentiment, MCP search backend, encryption (pysqlcipher3) — each import-guarded with
  graceful degradation and skip-if-missing tests.

---

## Final Acceptance (met)

- ✅ Grounded, cited, programmatically-validated Q&A · ✅ morning digest at market tz ·
  ✅ `/portfolio` (NL + command + CSV) + Exit Advisor + redeploy · ✅ one-shot deduped
  alerts · ✅ filings/macro/backtest/semantic (graceful) · ✅ `docker compose up` runs it
  anywhere, free, model-swappable · ✅ reproducible installs (uv.lock) · ✅ Groq + Ollama
  tool-calling · ✅ all guardrails verified · **174 tests passing.**

> **Durability note:** standalone repo outside fbsource; lost once to a Sandcastle recycle
> and rebuilt from the session transcript. Now backed up via **dotsync2** and with a
> **GitHub remote** (`ashuaeron/Financial-Advisor`); push from a machine with open internet.

---

# PHASE 5 — Enhancements (post-plan)

## 5A Exit Advisor + macro wired into the agent — DONE
- `agent/tools.py`: `assess_exit` (runs Exit Advisor for a stored/inline holding) and
  `get_macro` tools; registry gains optional `llm`; `app.py` passes it. Prompt routing hint.

## 5B LLM-enriched Exit Advisor — DONE
- `agent/exit_advisor.py`: `ExitVerdict.llm_rationale` + `enrich_exit_verdict()` (LLM
  refines transient/structural + rationale; deterministic action kept as backstop;
  no-op/safe if llm absent or errors). Wired into `assess_exit`.

## 5C Semantic Recall (detailed, planned)

Goal: meaning-based retrieval over articles/documents/analyses via local embeddings +
vector search, behind the `[semantic]` extra with graceful fallback. See design §16.

- **5C.1 Install extras** — `uv sync --extra semantic` (`sentence-transformers`,
  `sqlite-vec`). NOTE: pulls in PyTorch (large) — opt-in only. Add a clean-import check.
- **5C.2 Backend detection + schema** — `brain/semantic.py`: detect `sqlite-vec` (needs
  `enable_load_extension`), else `chromadb`, else `enabled=False`. When enabled, create the
  `vec_chunks` vec0 virtual table (dim 384) + a `chunks` metadata table. TDD: disabled-path
  test already exists; add an enabled-path init test (skipif backend missing).
- **5C.3 Embedding + chunking** — `embed_text(text, embed_fn=None)` (lazy
  `SentenceTransformer('all-MiniLM-L6-v2')`; **injectable `embed_fn` for tests**);
  `chunk_text(text, size≈500, overlap≈50)`. TDD: chunking boundaries; embed_fn injection
  returns a vector of expected dim.
- **5C.4 Index API** — `index_text(conn, kind, source_id, text, embed_fn=None)` chunks +
  embeds + inserts into `vec_chunks` + `chunks`; `index_all(conn)` backfills existing
  `articles`/`documents`. TDD with a fake deterministic `embed_fn` (no torch): index 2 docs,
  assert rows in both tables.
- **5C.5 Search** — `semantic_search(conn, query, k=5, embed_fn=None)` → embed query, KNN
  (cosine) over `vec_chunks`, join `chunks`, return `[(score, kind, source_id, text)]`. TDD
  with fake embeddings: nearest chunk to a query vector ranks first.
- **5C.6 Tool** — `recall_context(query)` in `ToolRegistry`, **registered only when
  `SemanticIndex.enabled`**; article/news chunks wrapped untrusted, documents trusted. TDD:
  with a stubbed enabled index, tool returns ranked context; when disabled, tool absent.
- **5C.7 Wire ingestion** — `data/documents.ingest_file` and `scheduler.daily_crawl_job`
  call `index_text` when semantic enabled; optional startup `index_all` backfill. TDD:
  ingest triggers indexing when enabled (mocked), no-op when disabled.
- **5C.8 Smoke test (real model)** — `skipif` sentence-transformers/sqlite-vec absent:
  index a tiny corpus, query a paraphrase, assert the semantically-related doc ranks top.
- **Acceptance:** with `[semantic]` installed, `recall_context("data-center demand")`
  surfaces a "GPU orders" article keyword search would miss; without it, the app runs
  unchanged (tool simply absent).
