"""
app/models/market_intelligence.py
Table for storing unstructured news text with embeddings for RAG.
"""
import uuid
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from app.core.db import Base

class MarketIntelligence(Base):
    __tablename__ = "market_intelligence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Using 768 dimensions as it's common for many text embedding models like Nomic or Instructor.
    # Adjust dimension based on the Gemini embedding model used.
    embedding: Mapped[list[float]] = mapped_column(Vector(768))

