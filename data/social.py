"""Work-stream C: Social & Search-Attention signals.

Best-effort, defensive social/attention data:
  - StockTwits per-symbol bullish/bearish sentiment ratio.
  - Reddit public-JSON mention volume + VADER sentiment over post titles.
  - Google Trends search-attention with spike detection (pytrends, LAZY/optional).

Design mirrors data/news.py + data/market.py conventions: typed dataclasses, an
``Unavailable`` marker (reused from data.market) for missing data, injectable
fetch/client callables so tests run OFFLINE with canned JSON (no network, no keys),
and any raw social text that could reach the model is wrapped via ``wrap_untrusted``.

KEY POLICY: an attention SPIKE is treated as a RISK signal (contrarian/hype guard),
not a buy signal. ``combined_social`` raises ``risk_flag`` when sentiment is extreme
AND attention is spiking.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agent.prompts import Citation, wrap_untrusted
from data.market import Unavailable
from data.news import news_sentiment
from http_client import get_json, get_text
from logging_setup import get_logger
from security.guards import validate_ticker

log = get_logger(__name__)


@dataclass
class SocialSignal:
    ticker: str
    bullish_ratio: float | None
    message_volume: int | None
    sentiment: float | None
    source: str
    as_of: str


@dataclass
class AttentionSignal:
    query: str
    attention: float | None
    attention_spike: bool
    baseline: float | None
    source: str
    as_of: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# StockTwits/Reddit bot-block the generic default UA, so use realistic ones. Reddit's public
# .json wants a unique descriptive UA (a browser UA there tends to get 429'd).
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_REDDIT_UA = "fin-advisor/1.0 (personal financial advisor; +https://github.com/)"


def _json_fetch(url: str, *, user_agent: str = _BROWSER_UA) -> dict | list:
    """JSON fetch with a realistic User-Agent + JSON Accept; falls back to text+parse.
    Raises on a non-JSON body so the caller degrades to Unavailable rather than mis-parsing."""
    headers = {"Accept": "application/json"}
    try:
        return get_json(url, user_agent=user_agent, headers=headers)
    except Exception:  # noqa: BLE001 - fall back to text+parse (may itself raise -> Unavailable)
        return json.loads(get_text(url, user_agent=user_agent, headers=headers))


def _default_fetch(url: str) -> dict | list:
    return _json_fetch(url)


def _reddit_fetch(url: str) -> dict | list:
    return _json_fetch(url, user_agent=_REDDIT_UA)


def _reddit_creds():
    """Free Reddit 'script' app credentials from env (trusted config), or None."""
    import os

    cid = os.environ.get("REDDIT_CLIENT_ID")
    csec = os.environ.get("REDDIT_CLIENT_SECRET")
    return (cid, csec) if cid and csec else None


def _reddit_praw_titles(ticker: str, subreddits, limit: int = 50) -> list[str]:
    """Read-only Reddit search via OAuth (praw). Requires the [social] extra + creds."""
    try:
        import praw
    except ImportError as e:  # pragma: no cover - optional dep
        raise RuntimeError("praw not installed; run: uv sync --extra social") from e
    creds = _reddit_creds()
    if not creds:  # pragma: no cover - guarded by caller
        raise RuntimeError("Reddit OAuth creds missing (REDDIT_CLIENT_ID/SECRET)")
    reddit = praw.Reddit(
        client_id=creds[0],
        client_secret=creds[1],
        user_agent=_REDDIT_UA,
        check_for_async=False,
    )
    reddit.read_only = True
    titles: list[str] = []
    for sub in subreddits:  # pragma: no cover - needs live OAuth
        for post in reddit.subreddit(sub).search(ticker, sort="new", limit=limit):
            if getattr(post, "title", ""):
                titles.append(post.title)
    return titles


def stocktwits_sentiment(ticker: str, *, fetch=None) -> SocialSignal | Unavailable:
    """Bullish/bearish ratio from StockTwits' per-symbol stream.

    Parses ``entities.sentiment.basic`` ("Bullish"/"Bearish") per message.
    ``fetch(url) -> dict`` is injectable for offline tests. Returns ``Unavailable``
    on any error (best-effort degradation).
    """
    try:
        t = validate_ticker(ticker)
    except ValueError as e:
        return Unavailable(field="social", ticker=ticker, reason=str(e))
    fetch = fetch or _default_fetch
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{t}.json"
    try:
        data = fetch(url)
        messages = data.get("messages", []) if isinstance(data, dict) else []
        bullish = 0
        bearish = 0
        for m in messages:
            entities = (m or {}).get("entities") or {}
            sentiment = entities.get("sentiment") or {}
            basic = (sentiment.get("basic") or "").strip().lower()
            if basic == "bullish":
                bullish += 1
            elif basic == "bearish":
                bearish += 1
        graded = bullish + bearish
        bullish_ratio = (bullish / graded) if graded else None
        return SocialSignal(
            ticker=t,
            bullish_ratio=bullish_ratio,
            message_volume=len(messages),
            sentiment=None,
            source="stocktwits",
            as_of=_now(),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("stocktwits failed for %s: %s", t, e)
        return Unavailable(field="social", ticker=t, reason=str(e))


def reddit_mentions(
    ticker: str,
    subreddits: tuple[str, ...] = ("wallstreetbets", "stocks"),
    *,
    fetch=None,
) -> SocialSignal | Unavailable:
    """Mention volume + VADER sentiment across subreddit search results.

    Counts posts (message_volume) and runs ``data.news.news_sentiment`` over the concatenated
    titles. ``bullish_ratio`` is None here. Degrades to ``Unavailable`` on error.

    Reddit blocks unauthenticated ``.json`` access (HTTP 403), so when no ``fetch`` is
    injected we prefer the **OAuth path via praw** using REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET
    (a free Reddit "script" app). Without those creds it falls back to the public ``.json``
    endpoint, which will usually 403 and degrade to ``Unavailable``. ``fetch(url) -> dict`` is
    injectable for offline tests (bypasses both paths).
    """
    try:
        t = validate_ticker(ticker)
    except ValueError as e:
        return Unavailable(field="social", ticker=ticker, reason=str(e))
    try:
        if fetch is None and _reddit_creds():
            titles = _reddit_praw_titles(t, subreddits)
        else:
            fetch = fetch or _reddit_fetch
            titles = []
            for sub in subreddits:
                url = (
                    f"https://www.reddit.com/r/{sub}/search.json?"
                    f"q={t}&restrict_sr=1&sort=new&limit=50"
                )
                data = fetch(url)
                children = ((data or {}).get("data") or {}).get("children") or []
                for c in children:
                    title = ((c or {}).get("data") or {}).get("title") or ""
                    if title:
                        titles.append(title)
        sentiment = news_sentiment(" ".join(titles)) if titles else None
        return SocialSignal(
            ticker=t,
            bullish_ratio=None,
            message_volume=len(titles),
            sentiment=sentiment,
            source="reddit",
            as_of=_now(),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("reddit failed for %s: %s", t, e)
        return Unavailable(field="social", ticker=t, reason=str(e))


def google_trends_attention(query: str, *, client=None) -> AttentionSignal | Unavailable:
    """Search-attention (Google Trends) with spike detection.

    ``client`` is an injectable callable returning a list of interest values (most
    recent last) so tests bypass pytrends entirely. When omitted, pytrends is
    LAZY-imported (RuntimeError if missing). Computes baseline = mean(all-but-last),
    attention = last value, attention_spike = last > baseline * 1.5. Returns
    ``Unavailable`` on error/empty data.
    """
    try:
        if client is None:
            client = _pytrends_client
        series = client(query)
        if not series:
            return Unavailable(
                field="attention", ticker=query, reason="no trends data"
            )
        attention = float(series[-1])
        prior = series[:-1]
        baseline = (sum(prior) / len(prior)) if prior else None
        spike = bool(baseline is not None and baseline > 0 and attention > baseline * 1.5)
        return AttentionSignal(
            query=query,
            attention=attention,
            attention_spike=spike,
            baseline=baseline,
            source="google_trends",
            as_of=_now(),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("google trends failed for %s: %s", query, e)
        return Unavailable(field="attention", ticker=query, reason=str(e))


def _pytrends_client(query: str) -> list[float]:  # pragma: no cover - needs network/dep
    """Default Google Trends client. LAZY-imports pytrends (optional extra)."""
    try:
        from pytrends.request import TrendReq
    except ImportError as e:
        raise RuntimeError(
            "pytrends not installed; run: uv sync --extra social"
        ) from e
    pytrends = TrendReq(hl="en-US", tz=0)
    pytrends.build_payload([query], timeframe="today 3-m")
    df = pytrends.interest_over_time()
    if df is None or df.empty or query not in df:
        return []
    return [float(v) for v in df[query].tolist()]


def combined_social(
    ticker: str,
    *,
    stocktwits_fetch=None,
    reddit_fetch=None,
    trends_client=None,
) -> dict:
    """Blend social + attention into one best-effort summary.

    Skips any component that returns ``Unavailable``. Emits ``Citation`` objects for
    numeric values, and wraps any raw social note text via ``wrap_untrusted``.

    RISK POLICY (contrarian/hype guard): ``risk_flag`` is True when sentiment is
    EXTREME (abs(sentiment) >= 0.5 OR bullish_ratio >= 0.8 OR bullish_ratio <= 0.2)
    AND ``attention_spike`` is True. An attention spike is a RISK signal (crowded /
    hype trade), never a buy signal.
    """
    t = validate_ticker(ticker)

    bullish_ratio: float | None = None
    sentiment: float | None = None
    attention: float | None = None
    attention_spike = False
    citations: list[Citation] = []

    st = stocktwits_sentiment(t, fetch=stocktwits_fetch)
    if isinstance(st, SocialSignal):
        bullish_ratio = st.bullish_ratio
        if bullish_ratio is not None:
            citations.append(
                Citation(
                    metric="stocktwits_bullish_ratio",
                    value=round(bullish_ratio, 3),
                    source=st.source,
                    timestamp=st.as_of,
                )
            )

    rd = reddit_mentions(t, fetch=reddit_fetch)
    if isinstance(rd, SocialSignal):
        sentiment = rd.sentiment
        if sentiment is not None:
            citations.append(
                Citation(
                    metric="reddit_sentiment",
                    value=round(sentiment, 3),
                    source=rd.source,
                    timestamp=rd.as_of,
                )
            )
        if rd.message_volume is not None:
            citations.append(
                Citation(
                    metric="reddit_message_volume",
                    value=rd.message_volume,
                    source=rd.source,
                    timestamp=rd.as_of,
                )
            )

    at = google_trends_attention(t, client=trends_client)
    if isinstance(at, AttentionSignal):
        attention = at.attention
        attention_spike = at.attention_spike
        if attention is not None:
            citations.append(
                Citation(
                    metric="search_attention",
                    value=attention,
                    source=at.source,
                    timestamp=at.as_of,
                )
            )

    extreme = bool(
        (sentiment is not None and abs(sentiment) >= 0.5)
        or (bullish_ratio is not None and (bullish_ratio >= 0.8 or bullish_ratio <= 0.2))
    )
    risk_flag = bool(extreme and attention_spike)

    if risk_flag:
        raw_note = (
            f"Contrarian/hype risk on {t}: extreme social sentiment coincides with a "
            "search-attention spike. Crowded/hype conditions raise reversal risk; treat "
            "the attention spike as a RISK signal, not a buy signal."
        )
    elif extreme:
        raw_note = (
            f"Social sentiment on {t} is extreme but search attention is not spiking; "
            "no crowd-hype confirmation."
        )
    elif attention_spike:
        raw_note = (
            f"Search attention on {t} is spiking but social sentiment is not extreme; "
            "watch for a developing move."
        )
    else:
        raw_note = f"Social signals on {t} are unremarkable."

    return {
        "ticker": t,
        "bullish_ratio": bullish_ratio,
        "sentiment": sentiment,
        "attention": attention,
        "attention_spike": attention_spike,
        "risk_flag": risk_flag,
        "note": wrap_untrusted(raw_note),
        "citations": citations,
    }
