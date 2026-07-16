"""Offline tests for the historical brain + learning loop (Work-stream D).

Decisions live in the canonical ``analyses`` table (created by ``init_db``); this module
adds ``signal_snapshots`` + ``decision_outcomes`` via ``ensure_signals_schema``.
"""

from brain.analyses import save_analysis
from brain.db import init_db
from brain.signals import (
    ensure_signals_schema,
    evaluate_decisions,
    recall_decisions,
    recall_signal_history,
    save_signal_snapshot,
    track_record,
)


def _db(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))  # creates analyses + friends
    ensure_signals_schema(conn)
    return conn


def test_ensure_schema_idempotent_and_no_error(tmp_path):
    conn = _db(tmp_path)
    # Calling twice must not raise and must leave the new tables in place.
    ensure_signals_schema(conn)
    ensure_signals_schema(conn)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"signal_snapshots", "decision_outcomes"} <= names
    # It must not have disturbed the canonical decision log.
    assert "analyses" in names


def test_snapshot_round_trip_preserves_json_blob(tmp_path):
    conn = _db(tmp_path)
    blob = {"technical": {"rsi": 71.5}, "event": ["oil_shock"], "social": {"wsb": 12}}
    sid = save_signal_snapshot(conn, "NVDA", blob, 123.45, source="test")
    assert isinstance(sid, int) and sid > 0

    save_signal_snapshot(conn, "NVDA", {"rsi": 40}, 130.0)
    hist = recall_signal_history(conn, "NVDA")
    assert len(hist) == 2
    assert hist[0].signals == {"rsi": 40}  # newest first
    assert hist[1].signals == blob  # nested JSON preserved
    assert hist[1].price == 123.45
    assert hist[1].source == "test"


def test_recall_decisions_reads_analyses_log(tmp_path):
    conn = _db(tmp_path)
    save_analysis(conn, "AAPL", "q1", "HOLD", "r1", 0.6, {"rsi": 55}, 100.0)
    save_analysis(conn, "AAPL", "q2", "SELL", "r2", 0.7, {"rsi": 80}, 120.0)
    save_analysis(conn, "MSFT", "q", "BUY", "r", 0.5, {}, 50.0)

    dec = recall_decisions(conn, "AAPL")
    assert len(dec) == 2
    assert dec[0].verdict == "SELL"  # newest first
    assert dec[1].verdict == "HOLD"


def test_evaluate_marks_sell_correct_when_price_fell(tmp_path):
    conn = _db(tmp_path)
    save_analysis(conn, "NVDA", "q", "SELL", "reason", 0.7, {}, 120.0)

    outcomes = evaluate_decisions(conn, "NVDA", current_price=100.0)
    assert len(outcomes) == 1
    assert outcomes[0].correct == 1  # SELL + price fell -> correct
    assert outcomes[0].price_then == 120.0
    assert outcomes[0].price_now == 100.0


def test_evaluate_marks_sell_incorrect_when_price_rose(tmp_path):
    conn = _db(tmp_path)
    save_analysis(conn, "NVDA", "q", "SELL", "reason", 0.7, {}, 120.0)

    outcomes = evaluate_decisions(conn, "NVDA", current_price=140.0)
    assert outcomes[0].correct == 0  # SELL + price rose -> incorrect


def test_evaluate_is_idempotent(tmp_path):
    conn = _db(tmp_path)
    save_analysis(conn, "NVDA", "q", "HOLD", "reason", 0.5, {}, 100.0)

    first = evaluate_decisions(conn, "NVDA", current_price=110.0)
    assert len(first) == 1
    # No un-evaluated decisions remain -> second call scores nothing new.
    second = evaluate_decisions(conn, "NVDA", current_price=200.0)
    assert second == []


def test_watch_is_non_directional(tmp_path):
    conn = _db(tmp_path)
    save_analysis(conn, "NVDA", "q", "WATCH", "reason", 0.5, {}, 100.0)
    outcomes = evaluate_decisions(conn, "NVDA", current_price=90.0)
    assert outcomes[0].correct is None


def test_track_record_accuracy_and_breakdown(tmp_path):
    conn = _db(tmp_path)
    # 3 directional calls: SELL correct, HOLD correct, BUY wrong -> 2/3.
    save_analysis(conn, "T", "q", "SELL", "r", 0.7, {}, 100.0)  # falls -> correct
    save_analysis(conn, "T", "q", "HOLD", "r", 0.6, {}, 100.0)  # rises -> correct
    save_analysis(conn, "T", "q", "BUY", "r", 0.6, {}, 100.0)  # falls -> wrong
    # One non-directional call that must be excluded from the hit-rate.
    save_analysis(conn, "T", "q", "WATCH", "r", 0.5, {}, 100.0)

    # SELL is correct when price is below 100; HOLD/BUY correct when >= 100.
    # Use a per-decision evaluation so directions differ:
    # Evaluate SELL and HOLD first (they share nothing), then reset via distinct tickers?
    # Simpler: evaluate all at price 80 -> SELL correct (80<100), HOLD wrong, BUY wrong.
    # To get 2/3 we evaluate with a price that makes exactly 2 correct.
    # At price 100: SELL wrong (100 not < 100), HOLD correct (>=), BUY correct (>=) -> 2/3.
    evaluate_decisions(conn, "T", current_price=100.0)

    tr = track_record(conn, "T")
    assert tr["total"] == 3  # WATCH excluded (correct is None)
    assert tr["correct"] == 2
    assert abs(tr["accuracy"] - (2 / 3)) < 1e-9
    assert tr["by_action"]["HOLD"]["accuracy"] == 1.0
    assert tr["by_action"]["BUY"]["accuracy"] == 1.0
    assert tr["by_action"]["SELL"]["accuracy"] == 0.0


def test_track_record_all_tickers_when_none(tmp_path):
    conn = _db(tmp_path)
    save_analysis(conn, "AAA", "q", "SELL", "r", 0.7, {}, 100.0)
    save_analysis(conn, "BBB", "q", "HOLD", "r", 0.6, {}, 100.0)
    evaluate_decisions(conn, "AAA", current_price=90.0)  # SELL correct
    evaluate_decisions(conn, "BBB", current_price=110.0)  # HOLD correct

    tr = track_record(conn)  # ticker=None -> across all
    assert tr["ticker"] is None
    assert tr["total"] == 2
    assert tr["correct"] == 2
    assert tr["accuracy"] == 1.0
