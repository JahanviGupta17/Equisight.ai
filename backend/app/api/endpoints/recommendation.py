"""
app/api/endpoints/recommendation.py
API endpoints for viewing and responding to recommendations.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID

from app.core.db import get_db
from app.models.recommendation import Recommendation, RecommendationStatus
from app.schemas.recommendation import RecommendationResponse, RecommendationStatusUpdate
from app.models.drift_event import DriftEvent
from app.services.recommendation import generate_recommendation_data

router = APIRouter()

@router.get("/portfolio/{portfolio_id}", response_model=List[RecommendationResponse])
async def get_recommendations(portfolio_id: UUID, db: AsyncSession = Depends(get_db)):
    """Fetch all recommendations for a specific portfolio."""
    result = await db.execute(
        select(Recommendation)
        .where(Recommendation.portfolio_id == portfolio_id)
        .order_by(Recommendation.created_at.desc())
    )
    return result.scalars().all()

@router.post("/generate/{drift_event_id}", response_model=RecommendationResponse)
async def create_recommendation_from_drift(drift_event_id: UUID, db: AsyncSession = Depends(get_db)):
    """Manually generate a recommendation for a given drift event."""
    # Check if recommendation already exists
    existing = await db.execute(select(Recommendation).where(Recommendation.drift_event_id == drift_event_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Recommendation already exists for this drift event.")
        
    event = await db.get(DriftEvent, drift_event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Drift event not found")
        
    portfolio_value = event.details.get("total_value", 0.0)
    rec_data = await generate_recommendation_data(str(event.portfolio_id), event.details, portfolio_value=portfolio_value)
    
    recommendation = Recommendation(
        portfolio_id=event.portfolio_id,
        drift_event_id=event.id,
        action=rec_data["action"],
        explanation=rec_data["explanation"],
        scenario_projection=rec_data["scenario_projection"],
        candidate_scores=rec_data["candidate_scores"],
        proposed_weights=rec_data["proposed_weights"],
        status=RecommendationStatus.PENDING
    )
    
    db.add(recommendation)
    await db.commit()
    await db.refresh(recommendation)
    return recommendation

@router.patch("/{recommendation_id}/status", response_model=RecommendationResponse)
async def update_recommendation_status(
    recommendation_id: UUID, 
    update_data: RecommendationStatusUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Accept, Reject, or Postpone a recommendation."""
    recommendation = await db.get(Recommendation, recommendation_id)
    if not recommendation:
        raise HTTPException(status_code=404, detail="Recommendation not found")
        
    recommendation.status = update_data.status
    
    # If Accepted and Rebalance, we would actually trigger Phase 5 execution loop here.
    
    await db.commit()
    await db.refresh(recommendation)
    return recommendation
