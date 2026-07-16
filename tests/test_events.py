import pandas as pd
import pytest

from agent.events import (
    confirm_with_price,
    detect_events,
    enrich_events,
    sector_for_ticker,
)
from agent.knowledge import load_sector_map
from config import ConfigError
from data.market import Unavailable
from data.worldnews import Headline


def _h(title, summary=""):
    return Headline(title=title, url="https://x", source="s", published_at="", summary=summary)


class FakeMarket:
    """Synthetic market: rising/falling/none per ETF for price confirmation tests."""

    def __init__(self, trends=None, sectors=None):
        self.trends = trends or {}
        self.sectors = sectors or {}

    def get_history(self, etf):
        t = self.trends.get(etf)
        if t == "up":
            return pd.DataFrame({"Close": [float(i) for i in range(1, 261)]})
        if t == "down":
            return pd.DataFrame({"Close": [float(i) for i in range(260, 0, -1)]})
        return Unavailable(field="history", ticker=etf, reason="no data")

    def get_sector(self, ticker):
        return self.sectors.get(ticker)


def test_detect_events_matches_theme():
    smap = load_sector_map()
    headlines = [
        _h("Iran strikes near Strait of Hormuz", "oil supply at risk"),
        _h("Tehran warns of escalation"),
        _h("Unrelated tech earnings beat"),
    ]
    events = detect_events(headlines, smap)
    themes = {e.theme for e in events}
    assert "middle_east_conflict" in themes
    mideast = next(e for e in events if e.theme == "middle_east_conflict")
    assert mideast.headline_count == 2
    assert "iran" in mideast.matched_keywords
    assert 0 < mideast.confidence <= 1.0
    sectors = {i["sector"] for i in mideast.impacts}
    assert {"energy", "defense", "airlines", "semiconductors"} <= sectors


def test_detect_events_no_match_returns_empty():
    smap = load_sector_map()
    assert detect_events([_h("quiet day in markets")], smap) == []


def test_confirm_with_price_agrees_and_disagrees():
    smap = load_sector_map()
    event = detect_events([_h("Iran and Israel escalate near Hormuz")], smap)[0]
    market = FakeMarket(
        trends={"XLE": "up", "ITA": "up", "JETS": "down", "SOXX": "down"}
    )
    confirm_with_price(event, market)
    by_etf = {i["etf"]: i["confirmed"] for i in event.impacts}
    assert by_etf["XLE"] is True  # expected up, market up
    assert by_etf["JETS"] is True  # expected down, market down

    # Now flip XLE to a falling market: expected up but market down -> not confirmed.
    event2 = detect_events([_h("Iran conflict near Hormuz")], smap)[0]
    confirm_with_price(event2, FakeMarket(trends={"XLE": "down"}))
    xle = next(i for i in event2.impacts if i["etf"] == "XLE")
    assert xle["confirmed"] is False


def test_confirm_with_price_unavailable_is_none():
    smap = load_sector_map()
    event = detect_events([_h("Iran near Hormuz")], smap)[0]
    confirm_with_price(event, FakeMarket(trends={}))  # everything Unavailable
    assert all(i["confirmed"] is None for i in event.impacts)


def test_enrich_events_noop_without_llm():
    assert enrich_events([_h("anything")], None) == []


def test_sector_for_ticker():
    market = FakeMarket(sectors={"XOM": "Energy"})
    assert sector_for_ticker("XOM", market) == "Energy"
    assert sector_for_ticker("ZZZ", market) is None


def test_load_sector_map_valid():
    smap = load_sector_map()
    assert "middle_east_conflict" in smap
    impacts = smap["middle_east_conflict"]["impacts"]
    assert impacts["energy"]["etf"] == "XLE"
    assert impacts["energy"]["direction"] == "up"


def test_load_sector_map_missing_keywords(tmp_path):
    bad = tmp_path / "sector_map.yaml"
    bad.write_text(
        "themes:\n  t1:\n    impacts:\n      energy: {direction: up, etf: XLE}\n"
    )
    with pytest.raises(ConfigError):
        load_sector_map(bad)


def test_load_sector_map_bad_direction(tmp_path):
    bad = tmp_path / "sector_map.yaml"
    bad.write_text(
        "themes:\n  t1:\n    keywords: [x]\n    impacts:\n"
        "      energy: {direction: sideways, etf: XLE}\n"
    )
    with pytest.raises(ConfigError):
        load_sector_map(bad)


def test_load_sector_map_missing_etf(tmp_path):
    bad = tmp_path / "sector_map.yaml"
    bad.write_text(
        "themes:\n  t1:\n    keywords: [x]\n    impacts:\n"
        "      energy: {direction: up}\n"
    )
    with pytest.raises(ConfigError):
        load_sector_map(bad)
