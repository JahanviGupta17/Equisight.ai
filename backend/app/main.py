"""
app/main.py
FastAPI application factory.

Startup (lifespan):
  1. create_all_tables() — idempotent.
  2. APScheduler job for daily drift check (replaces Celery beat).

Shutdown:
  1. Stop scheduler.
  2. Dispose async engine.
"""
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.db import create_all_tables, dispose_engine

# ── Router imports ────────────────────────────────────────────────────────
from app.api.endpoints.portfolio import router as portfolio_router
from app.api.endpoints.upload import router as upload_router
from app.api.endpoints.market_data import router as market_data_router
from app.api.endpoints.optimizer import router as optimizer_router
from app.api.endpoints.recommendation import router as recommendation_router
from app.api.endpoints.preferences import router as preferences_router
from app.api.endpoints.chat import router as chat_router
from app.api.endpoints.admin import router as admin_router

os.makedirs("logs", exist_ok=True)

_stream_handler = logging.StreamHandler(sys.stdout)
try:
    _stream_handler.stream.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("logs/app.log", encoding="utf-8"),
        _stream_handler,
    ],
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Equisight.ai starting up — creating database tables...")
    await create_all_tables()
    logger.info("Database ready.")

    # APScheduler: daily drift check at 15:45 IST (replaces Celery beat + worker).
    # The job runs run_daily_drift_check() as a coroutine inside this event loop,
    # so advisory tasks spawned from it share the same process and WebSocket manager.
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from app.tasks.drift import run_daily_drift_check
    from app.workers.news_ingestion import run_news_ingestion

    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(run_daily_drift_check, "cron", hour=15, minute=45)
    # News ingestion: every 3 hours so RAG context stays fresh throughout trading day
    scheduler.add_job(run_news_ingestion, "interval", hours=3, id="news_ingestion")
    scheduler.start()
    logger.info("APScheduler started — drift check at 15:45 IST, news ingestion every 3h.")

    # Kick off an immediate first ingestion on startup (don't await — non-blocking)
    asyncio.create_task(run_news_ingestion())

    yield

    logger.info("Equisight.ai shutting down...")
    scheduler.shutdown(wait=False)
    await dispose_engine()


# ── App factory ───────────────────────────────────────────────────────────
app = FastAPI(
    title="Equisight.ai",
    description=(
        "Real-time portfolio optimization pipeline for Indian equities, ETFs, "
        "and mutual funds."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "detail": "An unexpected error occurred. Our team has been notified.",
        },
    )


# ── Routers ───────────────────────────────────────────────────────────────
API_V1_PREFIX = "/api/v1"

app.include_router(portfolio_router, prefix=API_V1_PREFIX)
app.include_router(upload_router, prefix=API_V1_PREFIX)
app.include_router(market_data_router, prefix=API_V1_PREFIX)
app.include_router(optimizer_router, prefix=API_V1_PREFIX)
app.include_router(recommendation_router, prefix=f"{API_V1_PREFIX}/recommendations", tags=["Recommendations"])
app.include_router(preferences_router, prefix=API_V1_PREFIX)
app.include_router(chat_router, prefix=API_V1_PREFIX)
app.include_router(admin_router, prefix=API_V1_PREFIX)


@app.get("/health", tags=["Health"], summary="Health check")
@app.get("/api/v1/health", tags=["Health"], summary="Health check (versioned)")
async def health_check() -> dict:
    return {"status": "ok", "service": "equisight.ai", "version": "0.1.0"}


# ── WebSockets ───────────────────────────────────────────────────────────
from app.services.websocket_manager import manager


@app.websocket("/api/v1/ws/{portfolio_id}")
async def websocket_endpoint(websocket: WebSocket, portfolio_id: str):
    await manager.connect(websocket, portfolio_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, portfolio_id)
    except Exception as exc:
        logger.warning("WebSocket error for portfolio %s: %s", portfolio_id, exc)
        manager.disconnect(websocket, portfolio_id)
