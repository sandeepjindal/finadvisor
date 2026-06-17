from agent.tools import FORBIDDEN_NAME, ToolOutput, ToolRegistry
from brain.db import init_db
from data.market import Quote, Unavailable


class FakeMarket:
    def __init__(self, quote=None):
        self._quote = quote

    def get_quote(self, ticker):
        return self._quote

    def get_fundamentals(self, ticker):
        return Unavailable("fundamentals", ticker.upper(), "n/a")

    def get_history(self, ticker, period="1y"):
        return Unavailable("history", ticker.upper(), "n/a")


class FakeSearch:
    def search(self, query, max_results=5):
        from data.search import SearchHit

        return [SearchHit("Title", "https://x.test", "snippet")]


def _registry(tmp_path, quote=None):
    conn = init_db(str(tmp_path / "brain.db"))
    return ToolRegistry(FakeMarket(quote), conn, search=FakeSearch())


def test_registry_has_expected_readonly_tools(tmp_path):
    reg = _registry(tmp_path)
    assert set(reg.names) == {
        "get_quote",
        "get_fundamentals",
        "get_technicals",
        "search_news",
        "recall_analysis",
        "read_playbook",
        "get_filings",
        "list_documents",
        "read_document",
        "search_documents",
    }


def test_no_tool_name_is_a_write_action(tmp_path):
    reg = _registry(tmp_path)
    assert not any(FORBIDDEN_NAME.search(n) for n in reg.names)


def test_get_quote_emits_citation(tmp_path):
    q = Quote(
        "NVDA",
        120.0,
        100.0,
        20.0,
        20.0,
        1000,
        "USD",
        "2026-06-16T00:00:00Z",
        "yfinance",
    )
    reg = _registry(tmp_path, quote=q)
    out = reg.call("get_quote", {"ticker": "NVDA"})
    assert isinstance(out, ToolOutput)
    assert any(c.metric == "price" and c.value == 120.0 for c in out.citations)


def test_search_news_is_wrapped_untrusted(tmp_path):
    reg = _registry(tmp_path)
    out = reg.call("search_news", {"query": "nvidia"})
    assert "<untrusted>" in out.text and "</untrusted>" in out.text


def test_read_playbook(tmp_path):
    reg = _registry(tmp_path)
    out = reg.call("read_playbook", {"topic": "exit_rules"})
    assert "stop" in out.text.lower()
