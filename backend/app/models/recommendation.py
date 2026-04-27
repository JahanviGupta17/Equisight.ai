"""
app/models/recommendation.py
SQLAlchemy model for Recommendations.
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
import enum
from .user import Base

class RecommendationAction(str, enum.Enum):
    HOLD = "Hold"
    REBALANCE = "Rebalance"
    REVIEW = "Review"

class RecommendationStatus(str, enum.Enum):
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"
    POSTPONED = "Postponed"

class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False)
    drift_event_id = Column(UUID(as_uuid=True), ForeignKey("drift_events.id"), nullable=True)
    
    # Core output
    action = Column(Enum(RecommendationAction), nullable=False)
    explanation = Column(Text, nullable=False)
    scenario_projection = Column(Text, nullable=False)
    
    # Metadata for transparency
    candidate_scores = Column(JSONB, nullable=True)
    proposed_weights = Column(JSONB, nullable=True)

    status = Column(Enum(RecommendationStatus), default=RecommendationStatus.PENDING, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
