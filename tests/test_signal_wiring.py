"""Loose-end wiring: macro/catalyst fed into the screener (no longer 0.5 placebos) and the
social hype-risk flag tightening the Exit Advisor's stop."""

from __future__ import annotations

from agent.events import DetectedEvent
from agent.exit_advisor import evaluate_exit
from agent.knowledge import load_rules
from agent.screener import catalyst_score, macro_score_from_events
from brain.db import init_db
from brain.holdings import Holding
from data.market import Quote, Unavailable


def _event(theme, sector, direction, confirmed):
    return DetectedEvent(
        theme=theme,
        impacts=[{"sector": sector, "direction": direction, "etf": "X", "confirmed": confirmed}],
    )


def test_macro_score_from_events_neutral_and_directional():
    assert macro_score_from_events(None) == 0.5
    assert macro_score_from_events([]) == 0.5
    up = [_event("t", "energy", "up", True), _event("t2", "defense", "up", True)]
    down = [_event("t", "airlines", "down", True)]
    assert macro_score_from_events(up) > 0.5
    assert macro_score_from_events(down) < 0.5
    # Unconfirmed impacts do not move the score (reliability gate).
    assert macro_score_from_events([_event("t", "energy", "up", None)]) == 0.5


def test_catalyst_score_sector_and_attention():
    events = [_event("mideast", "energy", "up", True)]
    assert catalyst_score("energy", events) > 0.5
    assert catalyst_score("airlines", events) == 0.5  # different sector, unaffected
    # Attention spike is a RISK, not a catalyst — it lowers the score.
    assert catalyst_score("energy", events, attention_spike=True) < catalyst_score(
        "energy", events
    )


class _FakeMarket:
    def get_quote(self, t):
        return Quote(t.upper(), 100.0, 99.0, 1.0, 1.0, 1000.0, "USD", "now", "test")

    def get_history(self, t, period="1y"):
        return Unavailable("history", t.upper(), "n/a")

    def get_fundamentals(self, t):
        return Unavailable("fundamentals", t.upper(), "n/a")


def test_social_risk_flag_tightens_exit_stop(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    rules = load_rules()
    h = Holding(0, "NVDA", 10.0, 50.0, "", "")
    base = evaluate_exit(h, _FakeMarket(), conn, rules)
    risky = evaluate_exit(
        h, _FakeMarket(), conn, rules, social={"risk_flag": True}
    )
    assert any("hype" in r.lower() or "crowding" in r.lower() for r in risky.reasons)
    # Tighter stop => a higher stop price than the un-flagged case (flat-% fallback path).
    assert risky.suggested_rule != base.suggested_rule
