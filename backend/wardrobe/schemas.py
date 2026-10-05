from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SaveLookRequest(BaseModel):
    user_id: UUID
    style_response: Dict[str, Any]
    name: Optional[str] = Field(default=None, max_length=150)


class SaveProductRequest(BaseModel):
    user_id: UUID
    product: Dict[str, Any]


class DeleteWardrobeRequest(BaseModel):
    user_id: UUID