from types import SimpleNamespace

from agent.prompts import Citation
from bot.formatting import chunk_message, format_answer


def test_short_message_single_chunk():
    assert chunk_message("hello") == ["hello"]


def test_long_message_chunked_under_limit():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(200))
    chunks = chunk_message(text, limit=2000)
    assert len(chunks) >= 2
    assert all(len(c) <= 2000 for c in chunks)
    assert "line 0" in chunks[0] and "line 199" in chunks[-1]


def test_overlong_single_line_hard_split():
    chunks = chunk_message("y" * 5000, limit=2000)
    assert all(len(c) <= 2000 for c in chunks)
    assert "".join(chunks) == "y" * 5000


def test_format_answer_has_verdict_citations_disclaimer():
    ans = SimpleNamespace(
        verdict="HOLD",
        text="NVDA is fine.\n\n⚠️ Not financial advice.",
        citations=[Citation("price", 120.0, "yfinance", "t")],
    )
    out = format_answer(ans)
    assert "**HOLD**" in out
    assert "price = 120.0 [yfinance]" in out
    assert "Not financial advice" in out
