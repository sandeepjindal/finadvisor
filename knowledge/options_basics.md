# Options Basics — Educational Playbook (Conservative First)

> Options are high-risk. A long option can lose **100% of the premium** you paid, and
> leverage magnifies losses. This is education, not a recommendation. **Not financial advice.**

## The two building blocks

- **Call** — the right (not obligation) to *buy* 100 shares at the **strike** by expiry.
  Buyers profit if the stock rises meaningfully above strike **before** time runs out.
- **Put** — the right to *sell* 100 shares at the strike by expiry. Buyers profit if the
  stock falls below strike.

One contract = 100 shares. The price you pay is the **premium** (per share, so ×100 in
dollars).

## Premium, and why it decays

Premium = intrinsic value (how far in-the-money) + time value. Time value **decays** every
day (theta) and goes to zero at expiry. If the move doesn't happen fast enough, a long
option loses value even when you were "right" on direction. This is the core reason naked
long calls so often expire worthless.

## Implied volatility (IV) and IV rank

- **IV** is the market's expected volatility priced into the option. Higher IV = more
  expensive premium.
- **IV rank / percentile** places today's IV within its own recent history (0–100%).
  - **High IV rank (rich):** options are expensive to *buy*. Favour **selling** premium
    (covered call / cash-secured put) rather than paying up for a long call.
  - **Low IV rank (cheap):** premium is relatively inexpensive — but you still risk 100%
    of it, so size small and pre-define your exit.

## Break-even

The underlying price where the trade neither makes nor loses money at expiry:
- **Call:** break-even = strike + premium
- **Put:** break-even = strike − premium

If break-even requires a large % move from spot in a short time, the odds are against you.

## Probability-ITM (POP)

An approximate chance the option finishes in-the-money, estimated from IV and time to
expiry (a zero-drift lognormal model; ignores drift, dividends, and skew — **approximate**).
A low POP (e.g. under ~35%) means the contract is effectively a lottery ticket that most
likely expires worthless.

## Unusual activity

When a contract's **volume > open interest**, more contracts traded today than were
outstanding — a crowd/attention signal. Treat it as a **RISK** flag (hype/crowding), never
as a buy signal.

## Conservative structures (prefer these)

- **Covered call:** you own 100+ shares and *sell* a call above the current price. You
  collect premium (income) and cap upside. Defined, modest risk — a beginner-appropriate
  income trade.
- **Cash-secured put (CSP):** you set aside cash to buy 100 shares and *sell* a put below
  the price. You get paid to wait and only buy if the stock dips to your strike.

Both **collect** premium and have far better-defined risk than buying options.

## The risks of naked long calls and leverage

- **100% loss:** if the stock doesn't move enough by expiry, the whole premium is gone.
- **Time works against you:** theta decay bleeds value daily.
- **Leverage cuts both ways:** small moves in the stock become large % swings in the
  option. Position size accordingly and never risk money you can't lose.
- Buying calls into **high IV** (e.g. right before earnings) often loses even on a correct
  direction call, because IV collapses afterward ("IV crush").

**Bottom line:** understand break-even, POP, and IV rank before trading; prefer conservative
income structures; keep positions small. **Not financial advice.**
