from unittest import mock

import data.documents as docs
from brain.db import init_db
from brain.documents import (
    get_document,
    list_documents,
    save_document,
    search_documents,
)
from data.documents import ingest_file, ingest_path, scan_inbox


def _db(tmp_path):
    return init_db(str(tmp_path / "brain.db"))


def test_store_and_search(tmp_path):
    conn = _db(tmp_path)
    save_document(conn, "text", "/x/a.txt", "a.txt", "NVDA datacenter demand strong")
    save_document(conn, "text", "/x/b.txt", "b.txt", "unrelated content")
    assert len(list_documents(conn)) == 2
    hits = search_documents(conn, "datacenter")
    assert len(hits) == 1 and hits[0].title == "a.txt"
    assert get_document(conn, "a.txt").kind == "text"


def test_ingest_txt_and_csv(tmp_path):
    conn = _db(tmp_path)
    txt = tmp_path / "note.txt"
    txt.write_text("my research on NVDA")
    csvf = tmp_path / "p.csv"
    csvf.write_text("ticker,shares\nNVDA,30\n")
    ingest_file(conn, str(txt))
    ingest_file(conn, str(csvf))
    titles = {d.title for d in list_documents(conn)}
    assert {"note.txt", "p.csv"} <= titles


def test_ingest_pdf_mocked(tmp_path):
    conn = _db(tmp_path)
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    with mock.patch.object(docs, "_extract_pdf", return_value="annual report text"):
        ingest_file(conn, str(pdf))
    assert get_document(conn, "report.pdf").clean_text == "annual report text"


def test_unsupported_and_oversize(tmp_path):
    bad = tmp_path / "x.bin"
    bad.write_text("data")
    try:
        ingest_path(str(bad))
        assert False
    except ValueError:
        pass
    big = tmp_path / "big.txt"
    big.write_text("x" * 100)
    try:
        ingest_path(str(big), max_bytes=10)
        assert False
    except ValueError:
        pass


def test_scan_inbox(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.pdf").write_bytes(b"x")
    (tmp_path / "ignore.bin").write_text("x")
    found = scan_inbox(str(tmp_path))
    assert len(found) == 2
