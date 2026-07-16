"""Optional heavy modules: verify graceful degradation / clear errors when the extra is
not installed (the state in this environment). If an extra IS installed, the relevant test
exercises the available path instead.
"""

import importlib.util
from types import SimpleNamespace

import pytest
from brain.db import init_db
from brain.semantic import semantic_backend, SemanticIndex


def _installed(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def test_semantic_disabled_without_backend(tmp_path):
    conn = init_db(str(tmp_path / "brain.db"))
    idx = SemanticIndex(conn)
    if semantic_backend() is None:
        assert idx.enabled is False
        assert idx.search("anything") == []
    else:  # pragma: no cover - depends on env
        assert idx.enabled is True


def test_finbert_missing_raises():
    from data.news import finbert_sentiment

    if not _installed("transformers"):
        with pytest.raises(RuntimeError):
            finbert_sentiment("good news")
    else:  # pragma: no cover
        assert isinstance(finbert_sentiment("good news"), float)


def test_openbb_provider_guard():
    from data.openbb_provider import openbb_available, OpenBBProvider

    if not openbb_available():
        with pytest.raises(RuntimeError):
            OpenBBProvider()
    else:  # pragma: no cover
        OpenBBProvider()


def test_mcp_search_backend_selectable_and_guarded():
    from data.search import get_search, MCPSearch

    s = get_search(SimpleNamespace(web_search_backend="mcp"))
    assert isinstance(s, MCPSearch)
    # No server configured -> a clear RuntimeError, never a silent/bad call.
    with pytest.raises(RuntimeError):
        s.search("q")


def test_encryption_guard():
    from brain.db import open_encrypted_db

    if not _installed("pysqlcipher3"):
        with pytest.raises(RuntimeError):
            open_encrypted_db("/tmp/enc.db", "key")
