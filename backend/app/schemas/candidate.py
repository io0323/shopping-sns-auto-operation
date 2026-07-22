import uuid
from datetime import date

from pydantic import BaseModel

from app.schemas.common import PageMeta


class CandidateOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    genre_name: str
    shop_name: str
    item_url: str
    image_url: str | None
    selected_date: date
    score: float
    score_breakdown: dict[str, float]
    status: str


class CandidateListResponse(BaseModel):
    items: list[CandidateOut]
    meta: PageMeta
