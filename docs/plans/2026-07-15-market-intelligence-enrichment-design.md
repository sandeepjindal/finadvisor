# Market Intelligence Enrichment — Design Document

**Date:** 2026-07-15
**Status:** Design — awaiting review before implementation
**Author:** Ashish (design dialogue with Claude)
**Companion:** builds on `2026-06-16-personal-financial-advisor-design.md`

---

## 0. Motivation

The agent's plumbing (tool loop, grounding, citations, LLM-enrichment hooks) is solid, but
the **analysis substance is thin**, which limits how much a user can trust its advice:

1. **Trend analysis is 3 hardcoded MA buckets** (`up`/`down`/`sideways`); MACD is computed
   but never used; there is no strength, slope, multi-timeframe, volume, or volatility.
2. **No awareness of external/geopolitical events** (war, sanctions, oil shocks) that move
   whole sectors — e.g. a US–Iran escalation lifts energy/defense and hits airlines/semis.
3. **No social / search-attention signal** — retail attention (Google Trends, Reddit/WSB,
   StockTwits) is both an early mover and a *risk* flag (hype precedes blow-ups).
4. **`macro` and `catalyst` signal families are hardcoded to `0.5`** in the screener — 25% of
   the composite score is currently placebo.

This document designs three work-streams that fix all four, wired into the existing
screener / Exit Advisor / digest / monitoring, and exposed as new read-only tools.

**Design principles carried over:** free & no-key-first, deterministic backstop + optional
LLM enrichment, config-over-code ("skills" in `knowledge/` + YAML), everything behind a
swappable interface, offline-testable with injectable clients, all external content treated
as `<untrusted>`.

---

## 1. Work-stream A — Enriched Trend Analysis

Turn the trend signal from 3 buckets into a **graded, multi-timeframe, confirmed** read.

### 1.1 `data/technicals.py` — richer `Technicals`
New fields (existing ones kept for backward-compat so current tests stay green):

| Field | Meaning | Derivation |
|---|---|---|
| `trend_strength` | continuous −1..+1 | blend of SMA50 slope, price-vs-SMA50 distance, SMA50-vs-SMA200 gap |
| `macd_cross` | `bullish` / `bearish` / `none` | MACD line vs signal crossover (**activates the dead MACD signal**) |
| `cross_signal` | `golden` / `death` / `none` | SMA50 crossing SMA200 in the recent window |
| `atr` | average true range (volatility) | 14-period ATR |
| `volume_ratio` | today vs 20-day avg volume | confirmation / unusual-activity flag |

`trend` stays as a coarse label but is now derived from `trend_strength` thresholds.

### 1.2 Multi-timeframe
Compute indicators on a **short window (≈3m)** and a **long window (≈1y)** and expose both.
This is what actually powers **transient vs structural**:
- short-term down **inside** long-term up → *transient* pullback
- both down (esp. with a death cross / MACD bearish) → *structural* break

### 1.3 `agent/exit_advisor.py`
Replace the single `above_200ma` boolean with a small evidence set:
- multi-timeframe agreement, `macd_cross`, `cross_signal`, `trend_strength`.
- **ATR-sized trailing stop** (`k × ATR`) instead of a flat 12% — adapts to each stock's
  volatility. Flat % kept as fallback when ATR is unavailable.

### 1.4 `agent/screener.py`
`technical` family becomes a graded function of `trend_strength` (+ MACD/cross bonuses),
replacing the `{up:0.8, sideways:0.5, down:0.2}` lookup.

**Testing:** synthetic price frames (rising / falling / choppy / cross) → deterministic
assertions. No network.

---

## 2. Work-stream B — External / Geopolitical Factor Intelligence

Detect macro/geopolitical events in near-real-time, map them to affected **sectors**, then
**confirm against real price action** before letting them influence advice.

### 2.1 Data sources (all free, no key unless noted)

| Source | Adapter | Gives | Key? |
|---|---|---|---|
| **Google News RSS** | `data/worldnews.py` | topical world/event headlines by query | none |
| **GDELT 2.0 DOC API** | `data/worldnews.py` | global event volume + tone (escalation detection) | none |
| **FRED** (extend) | `data/macro.py` | add crude oil `DCOILWTICO`, treasury spreads | free key (already used) |
| **yfinance futures** | `data/market.py` | `CL=F` crude, `GC=F` gold as fast macro proxies | none |
| **ddgs web search** | `data/search.py` (reuse) | on-demand event lookups | none |
| **SEC EDGAR** (reuse) | `data/filings.py` | company-specific risk language | none |

### 2.2 `knowledge/sector_map.yaml` (new editable "skill")
Event **theme → impacted sectors → ETF proxy + direction + rationale**. Tunable without
code, same philosophy as `rules.yaml`:

```yaml
themes:
  middle_east_conflict:
    keywords: [iran, israel, strait of hormuz, oil embargo, tehran, houthi]
    impacts:
      energy:         {direction: up,   etf: XLE,  why: oil supply risk}
      defense:        {direction: up,   etf: ITA,  why: military spend}
      airlines:       {direction: down, etf: JETS, why: jet-fuel cost}
      semiconductors: {direction: down, etf: SOXX, why: supply/logistics risk}
  rate_shock:
    keywords: [rate hike, fed funds, hawkish, inflation surprise]
    impacts:
      technology:     {direction: down, etf: XLK}
      financials:     {direction: up,   etf: XLF}
```

### 2.3 `agent/events.py` (new) — mapping engine
- `detect_events(headlines, sector_map)` — deterministic keyword → theme → impacted
  sectors + ETF proxies + a headline-count/tone confidence.
- **Price confirmation (reliability gate):** for each impacted sector ETF, pull its trend
  via Work-stream A. Only surface an impact as *active* when the market is actually moving
  that way — filters out headlines the market shrugged off.
- `enrich_events(...)` — optional LLM layer for **novel events not in the map** (best-effort,
  mirrors `enrich_exit_verdict`; deterministic map is the backstop).
- Ticker → sector via `yfinance.info['sector']`, so any holding can be tested against
  active themes.

### 2.4 New tools (`agent/tools.py`)
- `scan_market_context()` → active themes + impacted sectors + confirming ETF trend + tone,
  with citations.
- `get_sector_impact(ticker)` → for one holding: its sector, any active theme hitting it,
  and the confirming price move.

### 2.5 Scheduler (`scheduler/jobs.py`)
`world_scan_job` ingests world/topic news into the brain daily so the **morning digest** and
**monitoring** reference the current macro backdrop, not just per-ticker data.

---

## 3. Work-stream C — Social & Search-Attention Signals

Retail attention is an early mover **and** a risk flag. We treat an attention *spike* as a
volatility/risk signal, not blindly bullish — this is the reliability stance.

### 3.1 Data sources (free-first; honest on limits)

| Source | Adapter | Gives | Cost / caveat |
|---|---|---|---|
| **Google Trends** | `pytrends` (`[social]` extra) | search interest over time = retail attention | free, unofficial, rate-limited/fragile → cache + backoff |
| **Reddit** | public `.json` endpoints or PRAW (`[social]`) | r/wallstreetbets, r/stocks mention volume + sentiment | free (PRAW needs a free app id/secret); `.json` no-key but rate-limited |
| **StockTwits** | `data/social.py` (httpx) | `streams/symbol/{T}.json` — native **bullish/bearish** tags + message volume | free, no key — the solid **X-for-stocks substitute** |
| **X / Twitter** | optional stub | tweets | ⚠️ **effectively paid now** ($100+/mo); scraping is fragile/ToS-violating → optional adapter only, off by default |

### 3.2 `data/social.py` (new)
- `attention(ticker)` → normalized attention score + `attention_spike` bool (vs baseline).
- `social_sentiment(ticker)` → blended bullish/bearish from StockTwits + Reddit, with a
  **contrarian risk flag** when sentiment is extreme *and* attention is spiking.
- All returns typed; all text wrapped `<untrusted>` (it is public data, never instructions).
- Injectable HTTP/client fns so tests run offline with canned JSON.

### 3.3 New tool + signal wiring
- Tool `get_social_signal(ticker)` → attention, social sentiment, spike/risk flag, citations.
- Feeds a new/expanded **`sentiment`/`catalyst`** contribution; attention spike raises the
  Exit Advisor's caution (tighter stop) rather than the buy score.

---

## 4. Integration — killing the placebo, feeding every consumer

The three work-streams converge on the **five-family composite** in `agent/screener.py`,
finally making `macro` and `catalyst` real (they are `0.5` constants today):

| Family | Today | After |
|---|---|---|
| fundamental | P/E bands | unchanged |
| technical | 3-bucket | **graded trend_strength + MACD + cross (A)** |
| sentiment | VADER | VADER **+ social bullish/bearish (C)** |
| macro | `0.5` stub | **FRED rates/oil + active theme tone (B)** |
| catalyst | `0.5` stub | **event impact on the ticker's sector (B) + attention spike (C)** |

Consumers updated: **screener/digest** (richer ranking + a "macro backdrop" line),
**Exit Advisor** (event + attention risk → transient/structural + stop sizing),
**monitoring** (alert when an active theme hits a holding's sector).

---

## 5. Guardrails (unchanged philosophy, extended)

- All social/news/event text → `wrap_untrusted` (delimiter-spoof neutralized). Capability
  restriction remains the real backstop; these tools are **read-only**, no exfil.
- SSRF-safe fetch for every new HTTP source (`is_safe_url`, timeouts, size caps, backoff).
- **Attention/hype is a risk signal, not a buy signal** — encoded so the bot never chases a
  meme pump. Extreme social sentiment + attention spike → *caution*, tighter stop.
- Every new numeric that reaches an answer emits a `Citation` (grounding validator enforces
  it — no fabricated attention/tone numbers).
- New external sources are **best-effort**: any failure degrades gracefully to
  `Unavailable`; the agent discloses missing data, never fabricates.

---

## 6. Dependencies & extras (`pyproject.toml`)

- `[social]` — `pytrends` (Google Trends), `praw` (Reddit). StockTwits/GDELT/Google-News use
  the existing `httpx`. All opt-in; app runs without them (tools simply absent, like the
  semantic pattern).
- No new base deps. X/Twitter deliberately **not** added (paid).

---

## 7. Phasing (TDD, offline-first — matches repo convention)

| Step | Deliverable | Test |
|---|---|---|
| **A1** | richer `Technicals` (strength, MACD cross, golden/death, ATR, volume) | synthetic frames |
| **A2** | multi-timeframe compute | short/long fixtures |
| **A3** | Exit Advisor uses MTF + MACD + ATR stop | verdict assertions |
| **A4** | screener graded technical | score monotonicity |
| **B1** | `data/worldnews.py` (Google News RSS + GDELT) | canned feeds |
| **B2** | `knowledge/sector_map.yaml` + `load` validation | schema test |
| **B3** | `agent/events.py` detect + price-confirm + LLM enrich | fake headlines + fake trend |
| **B4** | `scan_market_context` / `get_sector_impact` tools | registry + citation tests |
| **B5** | `world_scan_job` | job unit test (mocked) |
| **B6** | wire macro+catalyst into screener | composite no longer constant |
| **C1** | `data/social.py` (StockTwits + Reddit .json + Google Trends) | canned JSON, injectable client |
| **C2** | `get_social_signal` tool + risk-flag logic | spike/contrarian assertions |
| **C3** | social feeds sentiment/catalyst + Exit Advisor caution | end-to-end score test |

Sequencing: **A → B → C** (B's price-confirmation and C's risk flag both reuse A's graded
trend). Each step: failing test → implement → green → `git commit -m "[finadv] Step ..."`.

---

## 8. Acceptance

- "What's NVDA looking like?" → graded trend + MACD/cross + attention + any active theme.
- "US–Iran conflict — what's affected?" → `scan_market_context` names energy/defense ↑,
  airlines/semis ↓, each **confirmed by its sector ETF's real move**, with citations.
- "Should I sell my JETS?" → Exit Advisor cites the oil/airlines theme + ATR-sized stop.
- Meme spike on a holding → attention-spike **risk** flag, tighter stop, no hype-chasing.
- Without `[social]` installed, everything else runs unchanged (social tools absent).

---

## 9. Honest limitations

- **Google Trends / Reddit .json** are unofficial/rate-limited — cache + backoff, treat as
  best-effort enrichment, never a hard dependency.
- **X/Twitter** is not free anymore; StockTwits + Reddit are the practical substitutes.
- **Discord/private channels** can't be read generically without being an authorized bot in
  each server — out of scope; StockTwits/Reddit cover the public retail-chatter signal.
- Event→sector mapping is a **heuristic** confirmed by price; it surfaces *hypotheses with
  evidence*, not predictions. The mandatory "Not financial advice." disclaimer stays.
```
