# Exit Rules

How to decide HOLD / TRIM / SELL. The core discipline of this advisor.

## Distinguish temporary dips from structural breaks
- **Transient (usually HOLD / add):** macro noise, sector rotation, one-off headlines,
  short-term supply hiccups — thesis and guidance intact.
- **Structural (real SELL trigger):** guidance cut, demand collapse, competitive loss,
  deteriorating margins/balance sheet, broken growth story.

## Mechanical exit signals (thresholds in `rules.yaml`)
- **Trailing stop** breached (default `trailing_stop_pct`).
- **Trend break:** price closes below the 200-day MA, or 50-day crosses below 200-day.
- **Overbought + stretched:** RSI above `rsi_overbought` AND valuation in top
  `valuation_percentile` of its own history → consider trimming to lock gains.
- **Thesis broken:** the original reason you bought (from saved analyses) no longer holds.

## Output discipline
Always give: current gain/loss %, the 2–3 dominant signals, a concrete action
(HOLD / TRIM fraction / SELL), the rule to set (e.g. trailing stop level), what would
flip the call, and a capital-redeployment idea. End with "Not financial advice."
