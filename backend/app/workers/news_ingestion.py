"""
app/workers/news_ingestion.py

Automated Indian financial news ingestion pipeline.

Design goals
────────────
• Fast: fetch all feeds concurrently (asyncio.gather); skip articles already
  seen (Redis bloom/set); embed only the headline + summary (not full body)
  so each article costs one Gemini embed call rather than N chunk calls.
• Accurate: use only authoritative Indian financial RSS sources; extract
  ticker mentions from the headline against a static NSE symbol list stored
  in the payload so vector search can be filtered by ticker later.
• Resilient: any single feed failure is caught and logged; Redis and Qdrant
  failures degrade gracefully — the pipeline never crashes the scheduler.

Scheduling
──────────
Called from main.py APScheduler every 3 hours (see main.py).
Can also be triggered manually via  POST /api/v1/admin/ingest-news.

Qdrant payload schema per point
─────────────────────────────────
{
  "content":         "<headline>. <summary>",  # what gets embedded + retrieved
  "source_url":      "https://...",
  "source_name":     "Moneycontrol",
  "published_utc":   "2025-04-22T10:30:00",
  "ticker_mentions": ["RELIANCE.NS", "TCS.NS"],  # for payload filtering
}
"""

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx

from app.core.config import settings
from app.services.rag import _embed, _get_qdrant, COLLECTION_NAME

logger = logging.getLogger(__name__)

# ── RSS feed catalogue ────────────────────────────────────────────────────────
# All feeds verified as returning RSS entries (tested 2026-04-22).
FEEDS: list[dict[str, str]] = [
    {"name": "NDTV Profit",              "url": "https://feeds.feedburner.com/ndtvprofit-latest"},
    {"name": "Hindu BusinessLine Markets","url": "https://www.thehindubusinessline.com/markets/feeder/default.rss"},
    {"name": "Hindu BusinessLine Economy","url": "https://www.thehindubusinessline.com/economy/feeder/default.rss"},
    {"name": "Hindu BusinessLine MF",    "url": "https://www.thehindubusinessline.com/portfolio/mutual-funds/feeder/default.rss"},
    {"name": "LiveMint Markets",         "url": "https://www.livemint.com/rss/markets"},
    {"name": "LiveMint Companies",       "url": "https://www.livemint.com/rss/companies"},
    {"name": "Investing.com India",      "url": "https://in.investing.com/rss/news.rss"},
    {"name": "Investing.com Commodities","url": "https://in.investing.com/rss/commodities.rss"},
]

# ── Nifty 500 ticker fragments for mention detection ─────────────────────────
# A curated subset of frequently-traded NSE tickers (base names without .NS).
# Full detection would require a DB lookup — this set covers 80% of retail portfolios.
_NIFTY_TICKERS: list[str] = [
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","SBIN","BHARTIARTL",
    "ITC","KOTAKBANK","LT","BAJFINANCE","AXISBANK","ASIANPAINT","MARUTI","HCLTECH",
    "SUNPHARMA","WIPRO","ULTRACEMCO","TITAN","NTPC","POWERGRID","NESTLEIND","TECHM",
    "TATAMOTORS","TATASTEEL","ADANIENT","ADANIPORTS","BAJAJFINSV","ONGC","COALINDIA",
    "JSWSTEEL","HINDALCO","BPCL","DRREDDY","CIPLA","DIVISLAB","GRASIM","HEROMOTOCO",
    "EICHERMOT","UPL","SBILIFE","SHREECEM","INDUSINDBK","VEDL","TATACONSUM",
    "BRITANNIA","APOLLOHOSP","DABUR","PIDILITIND","MUTHOOTFIN","CHOLAFIN","HAVELLS",
    "MOTHERSON","BALKRISIND","BERGEPAINT","COLPAL","GODREJCP","MARICO","PAGEIND",
    "VOLTAS","WHIRLPOOL","SIEMENS","ABB","BOSCHLTD","CUMMINSIND","MCDOWELL","RADICO",
    "NAUKRI","POLICYBZR","ZOMATO","PAYTM","NYKAA","IRCTC","DMART","TRENT","VARUN",
    "NHPC","RECLTD","PFC","CANBK","BANKBARODA","PNB","UNIONBANK","FEDERALBNK","IDFCFIRSTB",
    "HDFCLIFE","ICICIGI","STARHEALTH","BAJAJ-AUTO","TVSMOTORS","ASHOKLEY","EXIDEIND",
    "AMBUJACEM","ACC","RAMCOCEM","GLAND","ALKEM","TORNTPHARM","AUROPHARMA","NATCOPHARM",
    "SAIL","NMDC","MOIL","APOLLOTYRE","MPHASIS","LTIM","PERSISTENT","COFORGE",
    "LTTS","CYIENT","KPIT","TATAELXSI","DIXON","AMBER","POLYCAB","KEI","ASTRAL",
    "SUPREMEIND","AAPL","MSFT","GOOGL","AMZN","TSLA","NVDA",  # US ADRs held by Indian investors
]

# Pre-compile a single regex for all tickers (word-boundary match, case-insensitive)
_TICKER_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in _NIFTY_TICKERS) + r")\b",
    re.IGNORECASE,
)


def _extract_tickers(text: str) -> list[str]:
    """Return de-duplicated list of NSE ticker symbols mentioned in text."""
    hits = _TICKER_RE.findall(text)
    return list({t.upper() + ".NS" for t in hits})


def _article_id(url: str, title: str) -> str:
    """Stable 16-char hex ID from URL+title — used as Qdrant point ID and Redis dedupe key."""
    raw = f"{url}|{title}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]   # 32 hex chars → valid UUID4-ish


def _parse_datetime(entry: Any) -> str:
    """Best-effort ISO-8601 UTC string from feedparser entry."""
    try:
        import time as _time
        t = entry.get("published_parsed") or entry.get("updated_parsed")
        if t:
            dt = datetime(*t[:6], tzinfo=timezone.utc)
            return dt.isoformat()
    except Exception:
        pass
    return datetime.now(timezone.utc).isoformat()


# ── Redis seen-set helper ─────────────────────────────────────────────────────

async def _is_seen(rc: Any, article_id: str) -> bool:
    """True if we've already ingested this article (Redis SISMEMBER). False on Redis error."""
    try:
        return bool(await rc.sismember("equisight:news:seen", article_id))
    except Exception:
        return False


async def _mark_seen(rc: Any, article_id: str) -> None:
    try:
        await rc.sadd("equisight:news:seen", article_id)
        # Expire the entire seen-set after 7 days so it doesn't grow forever
        await rc.expire("equisight:news:seen", 604800)
    except Exception:
        pass


# ── Single feed fetcher ───────────────────────────────────────────────────────

async def _fetch_feed(feed_meta: dict[str, str]) -> list[dict]:
    """
    Fetch one RSS feed and return a list of article dicts.
    Uses httpx for async HTTP; feedparser for XML parsing (sync, fast).
    Falls back to empty list on any network or parse error.
    """
    try:
        async with httpx.AsyncClient(
            timeout=12,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
        ) as client:
            resp = await client.get(feed_meta["url"])
            resp.raise_for_status()
            raw_xml = resp.text
    except Exception as exc:
        logger.warning("Feed fetch failed [%s]: %s", feed_meta["name"], exc)
        return []

    try:
        parsed = feedparser.parse(raw_xml)
    except Exception as exc:
        logger.warning("Feed parse failed [%s]: %s", feed_meta["name"], exc)
        return []

    articles = []
    for entry in parsed.entries[:20]:   # cap at 20 per feed per run
        title   = (entry.get("title") or "").strip()
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        # Strip basic HTML tags from summary
        summary = re.sub(r"<[^>]+>", " ", summary).strip()
        url     = entry.get("link") or entry.get("id") or ""

        if not title or not url:
            continue

        # Content = headline + first 200 words of summary (keeps embed cost low)
        summary_words = summary.split()[:200]
        content = title + ". " + " ".join(summary_words)

        articles.append({
            "id":             _article_id(url, title),
            "content":        content,
            "source_url":     url,
            "source_name":    feed_meta["name"],
            "published_utc":  _parse_datetime(entry),
            "ticker_mentions": _extract_tickers(title + " " + summary),
        })

    logger.info("Feed [%s] → %d articles", feed_meta["name"], len(articles))
    return articles


# ── Batch embed + upsert ──────────────────────────────────────────────────────

async def _ingest_articles(articles: list[dict], rc: Any) -> int:
    """
    For each new article (not in Redis seen-set):
      1. Embed content via Gemini embedding-001
      2. Upsert into Qdrant with full payload
      3. Mark as seen in Redis
    Returns count of newly ingested articles.
    """
    if not articles:
        return 0

    from qdrant_client.models import PointStruct
    import uuid as _uuid

    client = _get_qdrant()
    stored = 0
    points_batch: list[PointStruct] = []

    for art in articles:
        if await _is_seen(rc, art["id"]):
            continue

        embedding = await _embed(art["content"])
        if embedding is None:
            logger.debug("Skipping article (embed failed): %s", art["source_url"])
            continue

        # Use a deterministic UUID derived from the article ID so upsert is idempotent
        point_uuid = str(_uuid.UUID(art["id"].ljust(32, "0")[:32]))

        points_batch.append(
            PointStruct(
                id=point_uuid,
                vector=embedding,
                payload={
                    "content":          art["content"],
                    "source_url":       art["source_url"],
                    "source_name":      art["source_name"],
                    "published_utc":    art["published_utc"],
                    "ticker_mentions":  art["ticker_mentions"],
                },
            )
        )

        await _mark_seen(rc, art["id"])
        stored += 1

        # Upsert in batches of 20 to avoid large single requests
        if len(points_batch) >= 20:
            try:
                client.upsert(collection_name=COLLECTION_NAME, points=points_batch)
            except Exception as exc:
                logger.error("Qdrant upsert batch failed: %s", exc)
            points_batch = []

    # Flush remainder
    if points_batch:
        try:
            client.upsert(collection_name=COLLECTION_NAME, points=points_batch)
        except Exception as exc:
            logger.error("Qdrant upsert final batch failed: %s", exc)

    return stored


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_news_ingestion() -> dict[str, int]:
    """
    Full pipeline:
      1. Fetch all RSS feeds concurrently
      2. Deduplicate against Redis seen-set
      3. Embed + upsert new articles into Qdrant

    Returns {"fetched": N, "ingested": M} for monitoring.

    Redis unavailability is handled gracefully: a no-op sentinel is used
    that always reports unseen and silently swallows write errors.
    """
    if not settings.GEMINI_API_KEY:
        logger.warning("News ingestion skipped: GEMINI_API_KEY not set.")
        return {"fetched": 0, "ingested": 0}

    # ── Redis client (graceful degradation) ───────────────────────────────────
    rc = None
    try:
        import redis.asyncio as aioredis
        rc = aioredis.from_url(
            settings.CELERY_BROKER_URL,
            decode_responses=False,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        await rc.ping()
        logger.info("News ingestion: Redis connected.")
    except Exception as exc:
        logger.warning("News ingestion: Redis unavailable (%s) — deduplication disabled.", exc)

        # Null object — all operations succeed silently, deduplication disabled
        class _NoRedis:
            async def sismember(self, *a, **kw): return False
            async def sadd(self, *a, **kw): pass
            async def expire(self, *a, **kw): pass
            async def ping(self): pass

        rc = _NoRedis()

    # ── Fetch all feeds concurrently ──────────────────────────────────────────
    feed_results = await asyncio.gather(
        *[_fetch_feed(f) for f in FEEDS],
        return_exceptions=True,
    )

    all_articles: list[dict] = []
    for result in feed_results:
        if isinstance(result, list):
            all_articles.extend(result)

    # Deduplicate within this batch by article ID (multiple feeds can carry the same story)
    seen_ids: set[str] = set()
    unique_articles: list[dict] = []
    for art in all_articles:
        if art["id"] not in seen_ids:
            seen_ids.add(art["id"])
            unique_articles.append(art)

    logger.info("News ingestion: %d total articles fetched, %d unique.", len(all_articles), len(unique_articles))

    # ── Embed + upsert ────────────────────────────────────────────────────────
    ingested = await _ingest_articles(unique_articles, rc)
    logger.info("News ingestion complete: %d new articles indexed into Qdrant.", ingested)

    return {"fetched": len(unique_articles), "ingested": ingested}
