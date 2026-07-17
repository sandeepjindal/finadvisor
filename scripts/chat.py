"""Terminal REPL to chat with the advisor WITHOUT Discord — fast live testing.

Needs only GROQ_API_KEY in .env (or LLM_PROVIDER=ollama for local). Exercises the full
agent: Q&A, /watchlist, /portfolio, "I own ...", and "should I sell ..." (Exit Advisor) —
all against live Groq + Yahoo Finance.

Run:  uv run python scripts/chat.py
"""

from __future__ import annotations

import os
import sys

# Make the project root importable when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from agent import engine  # noqa: E402
from agent.tools import ToolRegistry  # noqa: E402
from bot.commands import handle_command  # noqa: E402
from bot.formatting import format_answer  # noqa: E402
from brain.db import init_db  # noqa: E402
from data.market import MarketData  # noqa: E402
from data.search import DDGSearch  # noqa: E402


def make_llm():
    provider = os.environ.get("LLM_PROVIDER", "groq").lower()
    if provider == "ollama":
        from llm.ollama_provider import OllamaProvider

        return OllamaProvider(os.environ.get("OLLAMA_MODEL", "llama3.1"))
    if provider == "claude":
        from llm.claude_provider import ClaudeProvider

        # api_key optional: falls back to `ant auth login` profile / ANTHROPIC_AUTH_TOKEN.
        return ClaudeProvider(
            os.environ.get("ANTHROPIC_API_KEY"),
            os.environ.get("CLAUDE_MODEL", "claude-opus-4-8"),
        )
    from llm.groq_provider import GroqProvider

    key = os.environ.get("GROQ_API_KEY")
    if not key:
        sys.exit("Set GROQ_API_KEY in .env (or LLM_PROVIDER=ollama for local).")
    return GroqProvider(key, os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"))


def main() -> None:
    conn = init_db(os.environ.get("DB_PATH", "./brain.db"))
    llm = make_llm()
    tools = ToolRegistry(
        market=MarketData(cache_conn=conn), conn=conn, search=DDGSearch(), llm=llm
    )
    max_iters = int(os.environ.get("MAX_TOOL_ITERS", "6"))

    print(
        "💬 Fin-Advisor CLI — ask anything; '/portfolio', '/watchlist', or 'I own ...'"
    )
    print("   Type 'quit' to exit.  ⚠️ Not financial advice.\n")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q or q.lower() in {"quit", "exit"}:
            break
        cmd = handle_command(conn, q)
        if cmd is not None:
            print("\n" + cmd + "\n")
            continue
        try:
            ans = engine.answer(q, conn, llm, tools, max_iters)
            print("\n" + format_answer(ans) + "\n")
        except Exception as e:  # noqa: BLE001
            print(f"\n⚠️ error: {e}\n")


if __name__ == "__main__":
    main()
