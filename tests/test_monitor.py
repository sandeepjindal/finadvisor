from agent.exit_advisor import ExitVerdict
from agent.knowledge import load_rules
from brain.db import init_db
from brain.holdings import add_holding
from scheduler.jobs import monitor_holdings_job


def _sell_eval(h, market, conn, rules):
    return ExitVerdict(h.ticker, "SELL", "structural", 42.0, ["overbought"], "stop @ X")


def _hold_eval(h, market, conn, rules):
    return ExitVerdict(h.ticker, "HOLD", "transient", 5.0, ["intact"])


def test_alert_emitted_once_then_cooldown(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    add_holding(conn, "NVDA", 30, 100)
    rules = load_rules()
    first = monitor_holdings_job(conn, None, rules, evaluate_fn=_sell_eval)
    assert len(first) == 1 and "NVDA" in first[0]
    second = monitor_holdings_job(conn, None, rules, evaluate_fn=_sell_eval)
    assert second == []


def test_hold_emits_no_alert(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    add_holding(conn, "NVDA", 30, 100)
    out = monitor_holdings_job(conn, None, load_rules(), evaluate_fn=_hold_eval)
    assert out == []
