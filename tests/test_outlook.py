"""Industry outlook — ranks industry/commodity ETFs by graded trend. Offline with a fake
market returning synthetic rising/falling price frames."""

from __future__ import annotations

import numpy as np
import pandas as pd

from agent.outlook import format_outlook, industry_outlook, outlook_citations
from data.market import Unavailable


def _frame(direction):
    n = 220
    if direction == "up":
        close = np.linspace(100, 200, n)
    elif direction == "down":
        close = np.linspace(200, 100, n)
    else:
        close = np.full(n, 150.0)
    return pd.DataFrame({"Close": close})


class _FakeMarket:
    # SOXX rising, XLE falling, XLK flat, GLD unavailable.
    _map = {"SOXX": "up", "XLE": "down", "XLK": "flat"}

    def get_history(self, etf, period="1y"):
        d = self._map.get(etf)
        if d is None:
            return Unavailable("history", etf, "n/a")
        return _frame(d)


def test_outlook_ranks_strongest_first():
    uni = {"AI & Semis": "SOXX", "Energy": "XLE", "Tech": "XLK", "Gold": "GLD"}
    reads = industry_outlook(_FakeMarket(), universe=uni)
    # Rising SOXX should rank first; falling XLE last among those with data;
    # the unavailable GLD (strength None) sinks to the very bottom.
    assert reads[0].etf == "SOXX" and reads[0].trend_strength > 0
    assert reads[-1].etf == "GLD" and reads[-1].trend_strength is None
    # Energy (down) should have negative strength and rank below flat Tech.
    strengths = {r.etf: r.trend_strength for r in reads}
    assert strengths["XLE"] < strengths["XLK"]


def test_outlook_citations_and_format():
    uni = {"AI & Semis": "SOXX", "Energy": "XLE"}
    reads = industry_outlook(_FakeMarket(), universe=uni)
    cites = outlook_citations(reads)
    assert any(c.metric.startswith("trend_strength:") for c in cites)
    out = format_outlook(reads)
    assert "Industry outlook" in out and "SOXX" in out and "Not financial advice" in out
