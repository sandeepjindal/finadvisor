from types import SimpleNamespace
from unittest import mock

import app


def _cfg():
    return SimpleNamespace(
        log_level="INFO",
        db_path=":memory:",
        llm_provider="groq",
        bot_platform="discord",
        discord_token="t",
        max_tool_iters=6,
    )


def _patches(cfg):
    return (
        mock.patch.object(app, "load_dotenv"),
        mock.patch.object(app, "load_config", return_value=cfg),
        mock.patch.object(app, "configure_logging"),
        mock.patch.object(app, "init_db", return_value="CONN"),
        mock.patch.object(app, "get_llm", return_value="LLM"),
        mock.patch.object(app, "MarketData"),
        mock.patch.object(app, "get_search"),
        mock.patch.object(app, "ToolRegistry", return_value="TOOLS"),
        mock.patch.object(app, "build_bot", return_value="BOT"),
        mock.patch.object(app, "build_whatsapp_server", return_value="WHATSAPP"),
    )


def test_load_dotenv_called_before_load_config():
    cfg = _cfg()
    manager = mock.Mock()
    p = _patches(cfg)
    with (
        p[0] as m_dotenv,
        p[1] as m_config,
        p[2],
        p[3],
        p[4],
        p[5],
        p[6],
        p[7],
        p[8],
        p[9],
    ):
        manager.attach_mock(m_dotenv, "load_dotenv")
        manager.attach_mock(m_config, "load_config")
        app.bootstrap()
    order = [name for name, _, _ in manager.mock_calls]
    assert order.index("load_dotenv") < order.index("load_config")


def test_bootstrap_returns_context():
    cfg = _cfg()
    p = _patches(cfg)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9]:
        ctx = app.bootstrap()
    assert ctx.conn == "CONN" and ctx.llm == "LLM" and ctx.bot == "BOT"
    assert ctx.tools == "TOOLS"
    assert ctx.whatsapp_server is None
