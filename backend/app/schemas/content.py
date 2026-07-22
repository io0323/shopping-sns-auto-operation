import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import PageMeta


class ContentOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    candidate_id: uuid.UUID
    product_name: str
    title: str
    description: str
    hashtags: list[str]
    x_post: str
    cta: str
    quality_score: float | None
    quality_breakdown: dict[str, int] | None
    eval_comment: str | None
    regen_count: int
    prompt_version: str
    status: str
    scheduled_at: datetime | None
    posted_at: datetime | None
    edited_by_human: bool
    created_at: datetime
    updated_at: datetime


class ContentListResponse(BaseModel):
    items: list[ContentOut]
    meta: PageMeta


class ContentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    hashtags: list[str] | None = None
    x_post: str | None = None
    cta: str | None = None
    scheduled_at: datetime | None = None


class GenerateRequest(BaseModel):
    candidate_ids: list[uuid.UUID]
