# Risk Management

Risk management is the only edge a beginner controls. Position sizing and stop discipline
matter more than entries. **Most retail day-traders lose money — survival comes first.**

## The 1% rule (position sizing)
Never risk more than a small fixed fraction of the account on a single trade — the default
here is **1%** (`daytrade.max_risk_per_trade`). Sizing is derived, not guessed:

```
risk_per_share = |entry − stop|
dollar_risk    = account_size × max_risk_per_trade      # e.g. 1% of the account
shares         = dollar_risk ÷ risk_per_share
```

The stop distance sets the share count — a wider stop means fewer shares, not more risk.
This keeps every loss roughly the same, survivable size regardless of volatility.

## Stop discipline
- Set the stop at the price where the setup is **invalidated** (structure), then size to it.
- The stop is mechanical: exit when it breaks. Do not widen it, average down, or "give it
  room." Moving a stop against the trade is how small losses become account-enders.
- Once in profit, trail the stop to lock gains; never let a winner become a loser.

## Risk:reward (R:R)
- R:R = potential reward ÷ risk. Require at least **1.5:1** (`daytrade.min_rr`); prefer 2:1+.
- A 2:1 trader can be right less than half the time and still come out ahead. A great entry
  with poor R:R is still a bad trade — stand aside.

## Max daily loss (the circuit breaker)
- Cap total daily loss (commonly ~2–3× the per-trade risk, e.g. 2–3 losing trades). Hit the
  cap → stop trading for the day. This prevents revenge-trading and tilt.
- Track outcomes honestly; a losing streak means reduce size or step away, not press harder.

## Leverage warning
Leverage and options magnify losses as fast as gains and can exceed the capital deployed.
Prefer un-leveraged, conservative sizing. The engine will never encourage reckless leverage.

**Not financial advice.**
