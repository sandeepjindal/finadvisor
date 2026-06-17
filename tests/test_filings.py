from data.filings import EDGAR_UA, extract_section, Filing, get_recent_filings

SUBMISSIONS = {
    "filings": {
        "recent": {
            "form": ["10-K", "8-K", "4"],
            "filingDate": ["2026-02-01", "2026-03-01", "2026-03-02"],
            "accessionNumber": ["0001-23-000001", "0001-23-000002", "0001-23-000003"],
            "primaryDocument": ["nvda-10k.htm", "nvda-8k.htm", "form4.htm"],
        }
    }
}


def test_get_recent_filings_filters_forms_and_sets_ua():
    seen = {}

    def fake_get(url, user_agent=None, **kw):
        seen["ua"] = user_agent
        return SUBMISSIONS

    filings = get_recent_filings(
        "NVDA", forms=("10-K", "8-K"), get=fake_get, cik_map={"NVDA": "0001045810"}
    )
    assert [f.form for f in filings] == ["10-K", "8-K"]
    assert all(isinstance(f, Filing) for f in filings)
    assert "1045810" in filings[0].url
    assert seen["ua"] == EDGAR_UA


def test_unknown_ticker_returns_empty():
    assert get_recent_filings("NVDA", get=lambda *a, **k: {}, cik_map={}) == []


def test_extract_section():
    text = "Intro. Risk Factors: competition is fierce. Other stuff."
    out = extract_section(text, "risk factors")
    assert "competition" in out
    assert extract_section(text, "nonexistent") == ""
