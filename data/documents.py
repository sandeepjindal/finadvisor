"""Ingest local documents (PDF/CSV/TXT/MD) into the brain. Size-guarded; user-trusted
local content. Step 3.7.
"""

from __future__ import annotations

import csv
import os

from brain.documents import save_document
from logging_setup import get_logger

log = get_logger(__name__)

MAX_BYTES = 5_000_000
_SUPPORTED = {".pdf", ".csv", ".txt", ".md"}


def _extract_pdf(path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(path)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _extract_csv(path: str) -> str:
    with open(path, newline="") as f:
        reader = csv.reader(f)
        return "\n".join(", ".join(row) for row in reader)


def _extract_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def ingest_path(path: str, max_bytes: int = MAX_BYTES) -> tuple[str, str, str]:
    """Return (kind, title, clean_text) for a supported file. Raises ValueError if
    unsupported or oversized."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in _SUPPORTED:
        raise ValueError(f"unsupported document type: {ext}")
    if os.path.getsize(path) > max_bytes:
        raise ValueError(f"file too large (> {max_bytes} bytes): {path}")
    title = os.path.basename(path)
    if ext == ".pdf":
        return "pdf", title, _extract_pdf(path)
    if ext == ".csv":
        return "csv", title, _extract_csv(path)
    return "text", title, _extract_text(path)


def scan_inbox(documents_dir: str) -> list[str]:
    found: list[str] = []
    for root, _dirs, files in os.walk(documents_dir):
        for name in files:
            if os.path.splitext(name)[1].lower() in _SUPPORTED:
                found.append(os.path.join(root, name))
    return found


def ingest_file(conn, path: str, max_bytes: int = MAX_BYTES) -> int:
    from brain.documents import get_document

    existing = get_document(conn, path)
    if existing is not None:
        return existing.id  # already ingested (dedupe by path)
    kind, title, text = ingest_path(path, max_bytes=max_bytes)
    return save_document(conn, kind, path, title, text)
