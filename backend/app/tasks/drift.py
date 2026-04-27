"""
app/tasks/drift.py

Advisory pipeline runs as asyncio background tasks inside the Uvicorn process.
This means the same event loop, same ConnectionManager._rooms, and instant
WebSocket delivery — no Celery worker, no Redis pub/sub bridge required.

Two entry points:
  generate_rag_advisory_task(portfolio_id, drift_event_id, triggering_asset)
    — called from optimizer.py via asyncio.create_task()

  run_daily_drift_check()
    — called from a lightweight APScheduler job in main.py
"""

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.drift_event import DriftEvent
from app.models.holding import Holding
from app.models.portfolio import Portfolio
from app.services import analytics as analytics_svc
from app.services import market_data as market_data_svc

logger = logging.getLogger(__name__)

RELATIVE_DRIFT_BAND = 0.20


# ---------------------------------------------------------------------------
# RAG Advisory — runs in-process as an asyncio task
# ---------------------------------------------------------------------------

async def generate_rag_advisory_task(
    portfolio_id: str,
    drift_event_id: str,
    triggering_asset: str,
) -> None:
    """
    Full pipeline — all async, all in Uvicorn's event loop.
    Emits advisory_progress WebSocket events at each stage so the frontend
    can show a live status card instead of a blank page.
    """
    import json
    from app.models.recommendation import Recommendation, RecommendationStatus
    from app.services.rag import retrieve_context
    from app.services.recommendation import generate_recommendation_data
    from app.services.websocket_manager import manager

    async def progress(step: str, message: str):
        await manager.broadcast_to_portfolio(
            portfolio_id,
            json.dumps({"type": "advisory_progress", "step": step, "message": message}),
        )

    engine = create_async_engine(settings.DATABASE_URL)
    SessionLocal = async_sessionmaker(engine)

    try:
        await progress("scanning", f"Scanning market intelligence for {triggering_asset}…")

        async with SessionLocal() as session:
            event = await session.get(DriftEvent, uuid.UUID(drift_event_id))
            if not event:
                logger.error("DriftEvent %s not found — aborting advisory.", drift_event_id)
                return

            drift_details = event.details
            total_value = drift_details.get("total_value", 0.0)

            await progress("retrieving", "Retrieving relevant news context from vector store…")
            rag_context = await retrieve_context(triggering_asset)

            await progress("thinking", "AI advisor is analysing your portfolio drift…")
            rec_data = await generate_recommendation_data(
                portfolio_id=portfolio_id,
                drift_details=drift_details,
                portfolio_value=total_value,
                rag_context=rag_context,
            )

            await progress("saving", "Finalising recommendation…")
            recommendation = Recommendation(
                portfolio_id=uuid.UUID(portfolio_id),
                drift_event_id=uuid.UUID(drift_event_id),
                action=rec_data["action"],
                explanation=rec_data["explanation"],
                scenario_projection=rec_data["scenario_projection"],
                candidate_scores=rec_data["candidate_scores"],
                proposed_weights=rec_data["proposed_weights"],
                status=RecommendationStatus.PENDING,
            )
            session.add(recommendation)
            await session.commit()
            await session.refresh(recommendation)

            await manager.broadcast_to_portfolio(
                portfolio_id,
                json.dumps({
                    "type": "new_recommendation",
                    "recommendation_id": str(recommendation.id),
                    "action": recommendation.action.value,
                    "explanation": recommendation.explanation,
                    "scenario_projection": recommendation.scenario_projection,
                    "proposed_weights": recommendation.proposed_weights,
                    "rag_sources": rec_data.get("rag_sources", []),
                    "drift_event_id": drift_event_id,
                }),
            )
            logger.info("RAG advisory generated and pushed for portfolio %s", portfolio_id)

    except Exception as exc:
        logger.error("RAG advisory task failed for portfolio %s: %s", portfolio_id, exc)
        await progress("error", "Advisory generation failed. Please re-analyse your portfolio.")
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Daily drift check — called by APScheduler, not Celery
# ---------------------------------------------------------------------------

async def run_daily_drift_check() -> None:
    """
    Scan all portfolios for drift vs target weights.
    Triggers generate_rag_advisory_task for any drifted portfolio.
    """
    engine = create_async_engine(settings.DATABASE_URL)
    SessionLocal = async_sessionmaker(engine)

    try:
        async with SessionLocal() as session:
            portfolios = (await session.execute(select(Portfolio))).scalars().all()

            for portfolio in portfolios:
                holdings = (await session.execute(
                    select(Holding).where(Holding.portfolio_id == portfolio.id)
                )).scalars().all()

                if not holdings:
                    continue

                symbols = [h.asset_symbol for h in holdings]
                try:
                    price_data = await market_data_svc.fetch_prices(symbols)
                except Exception as exc:
                    logger.error("Price fetch failed for portfolio %s: %s", portfolio.id, exc)
                    continue

                enriched = [
                    {
                        "asset_symbol": h.asset_symbol,
                        "asset_type": h.asset_type,
                        "quantity": h.quantity,
                        "average_buy_price": h.average_buy_price,
                        "current_price": (price_data.get(h.asset_symbol) or {}).get("current_price"),
                    }
                    for h in holdings
                ]

                weights_result = analytics_svc.calculate_current_weights(enriched)
                current_weights = weights_result.get("weights", {})
                total_value = sum(
                    (e.get("quantity") or 0) * (e.get("current_price") or e.get("average_buy_price") or 0)
                    for e in enriched
                )

                target_weights: dict = getattr(portfolio, "target_weights", None) or {}
                if not target_weights:
                    logger.info("Portfolio %s has no target weights — skipping.", portfolio.id)
                    continue

                drifted = []
                for asset, curr_w in current_weights.items():
                    tgt_w = target_weights.get(asset)
                    if not tgt_w:
                        continue
                    rel = abs(curr_w - tgt_w) / tgt_w
                    if rel > RELATIVE_DRIFT_BAND:
                        drifted.append({
                            "asset": asset,
                            "current_weight": round(curr_w, 4),
                            "target_weight": round(tgt_w, 4),
                            "absolute_drift": round(abs(curr_w - tgt_w), 4),
                            "relative_drift_pct": round(rel * 100, 2),
                        })

                if not drifted:
                    continue

                logger.info("Drift detected for portfolio %s: %d assets", portfolio.id, len(drifted))

                event = DriftEvent(
                    portfolio_id=portfolio.id,
                    details={
                        "drift_band": f"{int(RELATIVE_DRIFT_BAND * 100)}% of target weight",
                        "drifts": drifted,
                        "total_value": total_value,
                    },
                )
                session.add(event)
                await session.flush()

                worst = max(drifted, key=lambda d: d["relative_drift_pct"])["asset"]
                asyncio.create_task(
                    generate_rag_advisory_task(str(portfolio.id), str(event.id), worst)
                )

            await session.commit()

    except Exception as exc:
        logger.error("Daily drift check failed: %s", exc)
    finally:
        await engine.dispose()
