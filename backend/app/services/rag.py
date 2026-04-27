"""
app/services/rag.py
Phase 4 RAG pipeline backed by Qdrant (local on-disk mode).

Why Qdrant instead of pgvector?
- Zero infrastructure: runs embedded in-process, persists to a local folder.
- No Postgres extension install required — works identically on Windows dev
  and any Linux/Docker deployment target.
- Production path: swap QdrantClient(path=...) for
  QdrantClient(url="http://qdrant:6333") with a single env-var change.
- HNSW index is built automatically; no manual DDL.
- Cosine similarity, filtering, and payload storage are first-class features.
"""

import logging
import uuid
from typing import Optional

from google import genai as genai_client
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "market_intelligence"
EMBED_MODEL     = "gemini-embedding-001"        # 3072-dim, available on free tier
FLASH_MODEL     = settings.GEMINI_MODEL
VECTOR_DIM      = 3072
CHUNK_SIZE      = 400                           # words per chunk
CHUNK_OVERLAP   = 50                            # word overlap between chunks


# ---------------------------------------------------------------------------
# Qdrant client — lazy singleton
# ---------------------------------------------------------------------------
_qdrant_client = None


def _get_qdrant() :
    """
    Return (or create) the process-level Qdrant client.

    Local mode  (default): data stored under QDRANT_PATH from settings.
    Remote mode (prod):     set QDRANT_URL=http://qdrant:6333 in .env.
    """
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client

    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    if settings.QDRANT_URL:
        client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
        )
        logger.info("Qdrant: connected to remote server at %s", settings.QDRANT_URL)
    else:
        client = QdrantClient(path=settings.QDRANT_PATH)
        logger.info("Qdrant: using local on-disk storage at %s", settings.QDRANT_PATH)

    # Ensure the collection exists (idempotent)
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        logger.info("Qdrant: created collection '%s'", COLLECTION_NAME)

    _qdrant_client = client
    return client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunk_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i: i + size]))
        i += size - CHUNK_OVERLAP
    return chunks


async def _embed(text: str) -> Optional[list[float]]:
    if not settings.GEMINI_API_KEY:
        return None
    try:
        import httpx
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{EMBED_MODEL}:embedContent?key={settings.GEMINI_API_KEY}"
        )
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                url,
                json={"model": f"models/{EMBED_MODEL}", "content": {"parts": [{"text": text}]}},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]["values"]
    except Exception as exc:
        logger.warning("Embedding failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def ingest_article(
    content: str,
    source_url: str = "",
    source_name: str = "user_upload",
    ticker_mentions: list[str] | None = None,
) -> int:
    """
    Chunk, embed, and upsert an article into Qdrant.
    Returns the number of chunks stored.
    """
    chunks = _chunk_text(content)
    stored = 0

    try:
        from qdrant_client.models import PointStruct
        client = _get_qdrant()

        points = []
        for chunk in chunks:
            embedding = await _embed(chunk)
            if embedding is None:
                continue
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload={
                        "content":          chunk,
                        "source_url":       source_url,
                        "source_name":      source_name,
                        "ticker_mentions":  ticker_mentions or [],
                    },
                )
            )

        if points:
            client.upsert(collection_name=COLLECTION_NAME, points=points)
            stored = len(points)
            logger.info("Qdrant: ingested %d chunks for url=%s", stored, source_url or "n/a")

    except Exception as exc:
        logger.error("Qdrant article ingestion failed: %s", exc)

    return stored


async def retrieve_context(asset_symbol: str, top_k: int = 3) -> dict:
    """
    1. Embed the asset symbol query.
    2. ANN search in Qdrant (HNSW, cosine).
    3. Gemini Flash pre-summarization of retrieved chunks.

    Returns {"summary": str, "sources": [str]}
    Falls back gracefully to {"summary": "", "sources": []} on any error.
    """
    # Step 1: embed
    query_text = f"Indian market news analysis for {asset_symbol}"
    embedding = await _embed(query_text)
    if embedding is None:
        logger.info("Qdrant retrieve_context: no embedding (no API key?), skipping RAG.")
        return {"summary": "", "sources": []}

    # Step 2: vector search (qdrant-client >= 1.7 uses query_points)
    # Strategy: try ticker-filtered search first (fast + accurate); fall back
    # to unfiltered ANN if no results — handles assets not in the mention index.
    chunks: list[str] = []
    sources: list[str] = []
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchAny

        client = _get_qdrant()
        base_ticker = asset_symbol.split(".")[0].upper()

        # Attempt 1: filtered by ticker_mentions
        try:
            filtered_result = client.query_points(
                collection_name=COLLECTION_NAME,
                query=embedding,
                query_filter=Filter(
                    must=[FieldCondition(
                        key="ticker_mentions",
                        match=MatchAny(any=[asset_symbol, base_ticker]),
                    )]
                ),
                limit=top_k,
                with_payload=True,
            )
            hits = filtered_result.points
        except Exception:
            hits = []

        # Attempt 2: unfiltered semantic search if ticker filter returned nothing
        if not hits:
            result = client.query_points(
                collection_name=COLLECTION_NAME,
                query=embedding,
                limit=top_k,
                with_payload=True,
            )
            hits = result.points

        for hit in hits:
            if hit.payload:
                chunks.append(hit.payload.get("content", ""))
                src = hit.payload.get("source_url", "")
                if src:
                    sources.append(src)
    except Exception as exc:
        logger.warning("Qdrant search failed: %s", exc)
        return {"summary": "", "sources": []}

    if not chunks:
        logger.info("Qdrant: no chunks found for asset %s — RAG context empty.", asset_symbol)
        return {"summary": "", "sources": []}

    # Step 3: Flash pre-summarization
    if not settings.GEMINI_API_KEY:
        combined = "\n\n".join(chunks)
        return {"summary": combined[:2000], "sources": sources}

    try:
        client_genai = genai_client.Client(api_key=settings.GEMINI_API_KEY)
        flash_prompt = (
            f"Summarize the following news excerpts about {asset_symbol} "
            f"in 3-4 concise bullet points relevant to a portfolio rebalancing decision:\n\n"
            + "\n---\n".join(chunks)
        )
        response = await client_genai.aio.models.generate_content(
            model=FLASH_MODEL,
            contents=flash_prompt,
            config=types.GenerateContentConfig(max_output_tokens=300),
        )
        summary = response.text.strip()
    except Exception as exc:
        logger.warning("Flash summarization failed: %s", exc)
        summary = "\n".join(chunks[:2])

    return {"summary": summary, "sources": sources}
