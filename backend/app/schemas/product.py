import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.common import PageMeta


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_code: str
    name: str
    genre_id: str
    genre_name: str
    shop_code: str
    shop_name: str
    item_url: str
    image_url: str | None
    excluded: bool
    created_at: datetime
    updated_at: datetime


class ProductListResponse(BaseModel):
    items: list[ProductOut]
    meta: PageMeta


class ProductMetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    snapshot_date: date
    price: int
    point_rate: int
    review_count: int
    review_average: float
    rank: int | None
    rank_genre_id: str | None
