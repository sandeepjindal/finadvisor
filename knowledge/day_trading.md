# Day-Trading Playbook

Educational reference for the day-trade guidance engine. **Day trading is high-risk; most
retail traders lose money.** Nothing here is a recommendation to trade — it is a discipline
for *how* to trade if you choose to. Every plan must define entry, stop, target, and
risk:reward BEFORE entering. No bare "buy this."

## Core rule: plan the trade, trade the plan
A valid setup always specifies four numbers up front:
- **Entry** — the price/level that confirms the idea (not a hope).
- **Stop** — where the idea is wrong; exit mechanically, no negotiation.
- **Target** — a structure-based objective (measured move, prior level, VWAP).
- **Risk:reward (R:R)** — reward ÷ risk. Stand aside below ~1.5:1.

## The three setups this engine detects

### 1. Opening-range breakout
- Mark the high/low of the first ~30 minutes (the opening range, OR).
- Long only when price breaks **above** the OR high on **high relative volume** (≥ ~1.5×
  average bar volume). Short the mirror image below the OR low.
- Stop: the opposite side of the range. Target: a measured move (~2× the range height).
- No volume = no conviction = no trade.

### 2. Momentum (trend + VWAP)
- Trade in the direction of a strong daily trend (graded `trend_strength`).
- Long only while price **holds above VWAP**; short only while it stays **below VWAP**.
- Stop on a loss/reclaim of VWAP; trail the target as momentum extends (aim ≥ 2R).

### 3. Mean-reversion (RSI extreme → VWAP)
- Fade an intraday RSI extreme (≤30 oversold / ≥70 overbought) when price is stretched
  from VWAP. Target = reversion **to VWAP**; stop = one ATR beyond the extreme.
- Lowest-conviction setup — take only when R:R clears the minimum; otherwise stand aside.

## When to STAND ASIDE (the default)
- No clean setup: price chopping inside the opening range, weak/mixed trend, neutral RSI.
- Low relative volume (no participation).
- Risk:reward below the minimum (target too close for the required stop).
- Data delayed/unavailable (yfinance intraday is delayed and ~7 days for 1-minute bars).
Standing aside **is** a decision. Most of the day, it is the right one.

## Honest limits
Free intraday data is delayed and shallow — fine for guidance, not for HFT. Levels are
computed from bars, not live order flow. Always confirm on your own broker before acting.

**Not financial advice.**
