# Options Strategies — Conservative First

A ladder of options structures, safest first. Complements `options_basics` (the building
blocks: calls/puts, premium, theta, IV rank, break-even, POP). **Options are high-risk and
can lose money fast — this is education, not a recommendation.**

## Start here: income structures (defined, modest risk)
- **Covered call** — you already own 100+ shares and *sell* a call above the current price.
  You collect premium (income) and cap upside above the strike. Your real risk is just
  owning the stock; the call only forgoes gains past the strike. A sensible first options
  trade on a stock you're happy to hold or have called away.
- **Cash-secured put (CSP)** — you set aside cash to buy 100 shares and *sell* a put below
  the price. You get paid to wait and only buy if the stock dips to your strike — effectively
  a paid limit order. Only ever write CSPs on stocks you genuinely want to own at that price.
- Both **collect** premium and have far better-defined risk than buying options outright.

## Next: verticals / spreads (defined-risk directional)
- A **vertical spread** buys one option and sells another of the same type/expiry at a
  different strike. Both the **max gain and max loss are capped and known upfront** — the
  defining virtue for a beginner.
- **Bull call spread / bear put spread** (debit): pay a smaller net premium for a bounded
  directional bet — cheaper than a naked long option and the loss is capped at the debit.
- **Bull put spread / bear call spread** (credit): collect premium with a **defined** max
  loss (unlike a naked short option). Favoured when you want to sell premium without
  unlimited risk.
- Spreads trade some upside for capped, knowable downside — a fair deal for defined risk.

## When to sell vs buy premium (use IV rank)
- **High IV rank (premium is rich):** favour **selling** — covered calls, CSPs, credit
  spreads. You're selling expensive insurance; time decay (theta) works for you.
- **Low IV rank (premium is cheap):** buying a long option or debit spread is relatively
  cheaper — but you still risk 100% of what you pay, so size tiny and pre-define the exit.
- **Around earnings:** IV is inflated and collapses after the report ("IV crush", see
  `earnings_season`). Buying premium into earnings often loses even on a correct direction.

## The danger zone: naked long calls and leverage
- **Naked long call/put:** can lose **100% of the premium** if the move doesn't happen fast
  enough; theta bleeds it daily. Most expire worthless. A lottery ticket, not a strategy.
- **Naked short options** (uncovered calls especially): **theoretically unlimited loss** for
  a small premium. Do not do this. If you sell premium, define the risk with a spread.
- **Leverage cuts both ways:** small stock moves become large % swings in the option. Size
  by the *dollar risk* of the position (see `position_sizing`), never by the tempting notional.

## Discipline
- Climb the ladder in order: understand `options_basics` → income structures → defined-risk
  spreads. Don't skip to naked long calls because they look cheap.
- Every trade defines max loss, break-even, and an exit **before** entering. Keep each
  position small enough that the worst case is survivable.

**Educational only. Not financial advice.**
