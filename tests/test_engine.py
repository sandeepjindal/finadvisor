from agent import engine
from agent.tools import ToolRegistry
from brain.db import init_db
from data.market import Quote, Unavailable
from llm.base import LLMProvider, ToolCall, ToolCallResult


class FakeMarket:
    def __init__(self, quote=None):
        self._quote = quote

    def get_quote(self, ticker):
        return self._quote or Unavailable("quote", ticker.upper(), "n/a")

    def get_fundamentals(self, ticker):
        return Unavailable("fundamentals", ticker.upper(), "n/a")

    def get_history(self, ticker, period="1y"):
        return Unavailable("history", ticker.upper(), "n/a")


class FakeLLM(LLMProvider):
    def __init__(self, scripted=None, always_tools=False):
        self.scripted = list(scripted or [])
        self.always_tools = always_tools
        self.seen = []
        self.ask_called = 0

    def ask_with_tools(self, messages, tools):
        self.seen.append(list(messages))
        if self.scripted:
            return self.scripted.pop(0)
        if self.always_tools:
            return ToolCallResult(
                text=None, tool_calls=[ToolCall("cX", "get_quote", {"ticker": "NVDA"})]
            )
        return ToolCallResult(text="done. Not financial advice.", tool_calls=[])

    def ask(self, messages):
        self.ask_called += 1
        return "forced final. Not financial advice."

    def to_provider_tool_result(self, msg):
        return {}

    def parse_tool_calls(self, raw):
        return []


def _registry(conn, quote=None):
    return ToolRegistry(FakeMarket(quote), conn, search=None)


def test_tool_loop_executes_and_saves(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
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
    fake = FakeLLM(
        [
            ToolCallResult(
                text=None, tool_calls=[ToolCall("c1", "get_quote", {"ticker": "NVDA"})]
            ),
            ToolCallResult(text="NVDA looks fine. HOLD.", tool_calls=[]),
        ]
    )
    ans = engine.answer(
        "how is nvda?", conn, fake, _registry(conn, q), max_iters=6, ticker="NVDA"
    )
    assert ans.verdict == "HOLD"
    assert "Not financial advice" in ans.text
    assert any(c.value == 120.0 for c in ans.citations)
    assert conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 1


def test_tool_result_fed_back_in_messages(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    q = Quote("NVDA", 120.0, 100.0, 20.0, 20.0, 1000, "USD", "t", "yfinance")
    fake = FakeLLM(
        [
            ToolCallResult(
                text=None, tool_calls=[ToolCall("c1", "get_quote", {"ticker": "NVDA"})]
            ),
            ToolCallResult(text="ok. Not financial advice.", tool_calls=[]),
        ]
    )
    engine.answer("q", conn, fake, _registry(conn, q), ticker="NVDA")
    assert any(m.role == "tool" for m in fake.seen[1])


def test_grounding_flags_fabricated_number(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    fake = FakeLLM([ToolCallResult(text="Its P/E is 99.9, a buy.", tool_calls=[])])
    ans = engine.answer("q", conn, fake, _registry(conn), ticker="X")
    assert not ans.grounded
    assert 99.9 in ans.unsupported
    assert "Unverified" in ans.text


def test_rate_limit_degrades_gracefully(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))

    class RateLimitedLLM(FakeLLM):
        def ask_with_tools(self, messages, tools):
            raise RuntimeError("Error code: 429 - rate_limit_exceeded (tokens per day)")

    ans = engine.answer("any index funds?", conn, RateLimitedLLM(), _registry(conn), ticker=None)
    assert "rate limit" in ans.text.lower()
    assert ans.verdict == "INFO"  # no crash, friendly message


def test_generic_llm_error_degrades_gracefully(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))

    class BrokenLLM(FakeLLM):
        def ask_with_tools(self, messages, tools):
            raise RuntimeError("connection reset")

    ans = engine.answer("q", conn, BrokenLLM(), _registry(conn))
    assert "couldn't reach" in ans.text.lower() and ans.verdict == "INFO"


def test_iteration_cap_forces_final(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    q = Quote("NVDA", 120.0, 100.0, 20.0, 20.0, 1000, "USD", "t", "yfinance")
    fake = FakeLLM(always_tools=True)
    ans = engine.answer("q", conn, fake, _registry(conn, q), max_iters=3, ticker="NVDA")
    assert fake.ask_called == 1
    assert "forced final" in ans.text
    assert len(fake.seen) == 3
