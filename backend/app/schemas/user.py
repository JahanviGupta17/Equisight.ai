"""
app/schemas/user.py
Pydantic v2 schemas for User request/response validation.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["Priya Sharma"])
    email: EmailStr = Field(..., examples=["priya@example.com"])


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: EmailStr
    created_at: datetime
