# Position Sizing

How much to buy is a bigger decision than what to buy. Sizing is what keeps you in the game
long enough for your edge to play out. Complements `risk_management` — this is the how-much.

## The 1% risk rule
- **Risk a small, fixed fraction of the account per trade** — the default is **1%**
  (`daytrade.max_risk_per_trade`). "Risk" means the dollars lost if your stop is hit, not
  the dollars deployed.
- A string of losses is survivable when each is ~1%; it is fatal when each is 10%+. The rule
  exists so no single mistake can end you.
- Conservative long-term investors may risk even less per idea; speculative trades never more.

## Size = risk$ ÷ stop-distance
The share count falls out of the math — it is derived, never guessed:

```
dollar_risk    = account_size × max_risk_per_trade      # e.g. 1% of the account
risk_per_share = |entry − stop|
shares         = dollar_risk ÷ risk_per_share
```

- **The stop sets the size.** A wider (further) stop means *fewer* shares — same dollar
  risk — not a bigger bet. A tight stop lets you hold more shares for the same risk.
- Set the stop where the thesis is **invalidated** (structure), then size to it. Never widen
  the stop to justify a bigger position.

## Scaling in and out
- **Scale in:** build a full position in tranches (e.g. thirds) as the thesis confirms,
  rather than going all-in at one price. Averaging *up* into strength is fine; averaging
  *down* into a broken thesis is not.
- **Scale out:** trim into strength — take partial profit at a target, trail the rest. Locks
  gains while leaving upside. Trimming a winner is discipline, not weakness.
- Total risk across all tranches still respects the per-trade cap.

## Portfolio heat (the aggregate limit)
- **Heat = the sum of open risk** across all positions (what you'd lose if every stop hit).
  Cap it — e.g. **~5–6% total** — so a correlated bad day can't blow a hole in the account.
- Correlated positions share risk: five names in one sector are closer to one bet than five
  (see `diversification`). Count correlated risk once, not five times.
- Also respect a per-position weight ceiling (`max_position_weight`) regardless of stop math.

## Why sizing beats entry precision
- You control size exactly; you cannot control the entry fill or the outcome. Getting size
  right on an average entry beats a perfect entry on a reckless size.
- Correct sizing turns being wrong into a scratch and being right into a compounder. It is
  the one lever that works every single trade.
- **When uncertain, size down.** Half-size is a valid answer; full conviction is rare.

**Educational only. Not financial advice.**
