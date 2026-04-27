"""
app/schemas/recommendation.py
Pydantic schemas for Recommendations.
"""
from pydantic import BaseModel, UUID4
from typing import Optional, Dict, Any
from datetime import datetime
from app.models.recommendation import RecommendationAction, RecommendationStatus

class RecommendationBase(BaseModel):
    portfolio_id: UUID4
    drift_event_id: Optional[UUID4] = None
    action: RecommendationAction
    explanation: str
    scenario_projection: str
    candidate_scores: Optional[Dict[str, Any]] = None
    proposed_weights: Optional[Dict[str, float]] = None

class RecommendationCreate(RecommendationBase):
    pass

class RecommendationResponse(RecommendationBase):
    id: UUID4
    status: RecommendationStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class RecommendationStatusUpdate(BaseModel):
    status: RecommendationStatus
