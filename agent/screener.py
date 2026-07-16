"""Composite screener over the five signal families, weighted by rules.yaml. Step 2.2."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScreenScore:
    ticker: str
    composite: float
    breakdown: dict


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _fundamental_score(pe, profit_margin) -> float:
    if pe is None:
        f = 0.5
    elif pe <= 15:
        f = 1.0
    elif pe <= 25:
        f = 0.7
    elif pe <= 40:
        f = 0.4
    else:
        f = 0.2
    if isinstance(profit_margin, (int, float)) and profit_margin > 0.15:
        f += 0.1
    return _clamp(f)


def _technical_score(
    trend,
    rsi,
    rsi_overbought,
    trend_strength=None,
    macd_cross=None,
    cross_signal=None,
) -> float:
    """Graded technical score. When ``trend_strength`` (~ -1..+1) is available it maps
    linearly to 0..1 (monotonic in strength); otherwise falls back to the coarse
    up/sideways/down buckets. Small bonuses for a bullish MACD / golden cross (and
    penalties for the bearish/death counterparts). Work-stream A §1.4.
    """
    if isinstance(trend_strength, (int, float)):
        base = (trend_strength + 1.0) / 2.0
    else:
        base = {"up": 0.8, "sideways": 0.5, "down": 0.2}.get(trend, 0.5)
    if macd_cross == "bullish":
        base += 0.05
    elif macd_cross == "bearish":
        base -= 0.05
    if cross_signal == "golden":
        base += 0.05
    elif cross_signal == "death":
        base -= 0.05
    if isinstance(rsi, (int, float)) and rsi > rsi_overbought:
        base -= 0.2
    return _clamp(base)


def _sentiment_score(sentiment) -> float:
    if not isinstance(sentiment, (int, float)):
        return 0.5
    return _clamp((sentiment + 1.0) / 2.0)


def score_ticker(
    ticker: str,
    *,
    trend: str,
    rsi: float | None,
    pe: float | None,
    profit_margin: float | None,
    sentiment: float | None,
    rules,
    macro: float = 0.5,
    catalyst: float = 0.5,
    trend_strength: float | None = None,
    macd_cross: str | None = None,
    cross_signal: str | None = None,
) -> ScreenScore:
    w = rules.signal_weights
    overbought = rules.alert_thresholds.get("rsi_overbought", 70)
    parts = {
        "fundamental": _fundamental_score(pe, profit_margin),
        "technical": _technical_score(
            trend,
            rsi,
            overbought,
            trend_strength=trend_strength,
            macd_cross=macd_cross,
            cross_signal=cross_signal,
        ),
        "sentiment": _sentiment_score(sentiment),
        "macro": _clamp(macro),
        "catalyst": _clamp(catalyst),
    }
    composite = sum(parts[k] * w.get(k, 0.0) for k in parts)
    return ScreenScore(ticker, composite, parts)


def rank_universe(scores: list[ScreenScore]) -> list[ScreenScore]:
    return sorted(scores, key=lambda s: s.composite, reverse=True)


def macro_score_from_events(events) -> float:
    """Market-wide macro tone (0..1, 0.5 neutral) from confirmed geopolitical/macro impacts
    surfaced by the world scan. Net-positive confirmed impacts lift it; net-negative lower
    it. Replaces the old hardcoded 0.5 macro placebo (design §4/B6)."""
    if not events:
        return 0.5
    up = down = 0
    for e in events:
        for i in getattr(e, "impacts", []) or []:
            if not i.get("confirmed"):
                continue
            if i.get("direction") == "up":
                up += 1
            elif i.get("direction") == "down":
                down += 1
    return _clamp(0.5 + 0.05 * (up - down))


def catalyst_score(sector, events, attention_spike: bool = False) -> float:
    """Ticker catalyst (0..1, 0.5 neutral): active CONFIRMED themes hitting the ticker's
    sector push it up/down; a retail-attention spike is treated as a RISK (small penalty),
    never a buy catalyst. Replaces the old hardcoded 0.5 catalyst placebo."""
    score = 0.5
    if sector:
        for e in events or []:
            for i in getattr(e, "impacts", []) or []:
                same = str(i.get("sector", "")).lower() == str(sector).lower()
                if same and i.get("confirmed"):
                    score += 0.15 if i.get("direction") == "up" else -0.15
    if attention_spike:
        score -= 0.1
    return _clamp(score)
