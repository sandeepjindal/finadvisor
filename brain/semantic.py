"""Semantic recall over articles/documents. Optional ([semantic] extra). Gracefully
disables if neither sqlite-vec nor chromadb is available, so the agent still works.
Step 4.3.
"""

from __future__ import annotations

from logging_setup import get_logger

log = get_logger(__name__)


def semantic_backend() -> str | None:
    try:
        import sqlite_vec  # noqa: F401

        return "sqlite-vec"
    except ImportError:
        pass
    try:
        import chromadb  # noqa: F401

        return "chromadb"
    except ImportError:
        return None


class SemanticIndex:
    """Best-effort vector index. When no backend is installed, `enabled` is False and
    `search` returns [] — the engine simply doesn't register the recall_context tool."""

    def __init__(self, conn):
        self.conn = conn
        self.backend = semantic_backend()
        self.enabled = self.backend is not None
        if not self.enabled:
            log.info("semantic recall disabled (install .[semantic] to enable)")

    def _embed(self, text: str):  # pragma: no cover - requires model
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model.encode(text)

    def search(self, query: str, k: int = 5) -> list:
        if not self.enabled:
            return []
        # Full implementation depends on the installed backend; deliberately a no-op
        # placeholder until the [semantic] extra is installed and wired.
        return []  # pragma: no cover
