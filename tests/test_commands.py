from bot.commands import handle_command
from brain.db import init_db


def _db(tmp_path):
    return init_db(str(tmp_path / "brain.db"))


def test_add_list_remove_flow(tmp_path):
    conn = _db(tmp_path)
    assert "NVDA" in handle_command(conn, "/watchlist add NVDA ai leader")
    listed = handle_command(conn, "/watchlist list")
    assert "NVDA" in listed and "ai leader" in listed
    assert "Removed" in handle_command(conn, "/watchlist remove NVDA")
    assert "empty" in handle_command(conn, "/watchlist").lower()


def test_invalid_ticker_returns_warning(tmp_path):
    conn = _db(tmp_path)
    assert "⚠️" in handle_command(conn, "/watchlist add 12345")


def test_non_command_returns_none(tmp_path):
    conn = _db(tmp_path)
    assert handle_command(conn, "what about NVDA?") is None
