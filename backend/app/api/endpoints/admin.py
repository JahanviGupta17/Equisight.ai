"""
app/api/endpoints/admin.py
Internal operations endpoints — not user-facing.

POST /api/v1/admin/ingest-news   — manually trigger the news ingestion pipeline
"""
import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post(
    "/ingest-news",
    summary="Manually trigger news ingestion",
    description="Fetches all configured RSS feeds and upserts new articles into Qdrant. "
                "Runs in the background — returns immediately.",
)
async def trigger_news_ingestion() -> dict:
    import asyncio
    from app.workers.news_ingestion import run_news_ingestion

    asyncio.create_task(run_news_ingestion())
    return {"status": "triggered", "message": "News ingestion started in background."}
