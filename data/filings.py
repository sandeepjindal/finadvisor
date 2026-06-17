"""SEC EDGAR filings (10-K/10-Q/8-K). EDGAR requires a descriptive User-Agent or it 403s.
HTTP getter is injectable for offline tests. Step 4.1.
"""

from __future__ import annotations

from dataclasses import dataclass

from http_client import get_json
from security.guards import validate_ticker

EDGAR_UA = "fin-advisor/0.1 (personal financial advisor; contact: user@example.com)"
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


@dataclass
class Filing:
    ticker: str
    form: str
    date: str
    url: str


def _load_cik_map(get=get_json) -> dict[str, str]:
    data = get(_TICKERS_URL, user_agent=EDGAR_UA)
    rows = data.values() if isinstance(data, dict) else data
    return {str(r["ticker"]).upper(): str(r["cik_str"]).zfill(10) for r in rows}


def get_recent_filings(
    ticker: str,
    forms=("10-K", "10-Q", "8-K"),
    limit: int = 5,
    get=get_json,
    cik_map: dict[str, str] | None = None,
) -> list[Filing]:
    t = validate_ticker(ticker)
    cmap = cik_map if cik_map is not None else _load_cik_map(get)
    cik = cmap.get(t)
    if not cik:
        return []
    data = get(f"https://data.sec.gov/submissions/CIK{cik}.json", user_agent=EDGAR_UA)
    recent = data["filings"]["recent"]
    out: list[Filing] = []
    for form, date, acc, doc in zip(
        recent["form"],
        recent["filingDate"],
        recent["accessionNumber"],
        recent["primaryDocument"],
    ):
        if form in forms:
            accn = acc.replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{doc}"
            out.append(Filing(t, form, date, url))
            if len(out) >= limit:
                break
    return out


def extract_section(text: str, section: str, max_chars: int = 4000) -> str:
    """Crude section extractor: returns text following a heading match."""
    low = (text or "").lower()
    idx = low.find(section.lower())
    if idx == -1:
        return ""
    return text[idx : idx + max_chars]
