import uuid
from datetime import datetime

from pydantic import BaseModel


class ExportItem(BaseModel):
    content_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    item_url: str
    room_text: str
    x_text: str
    has_ad_disclosure: bool
    checklist: list[str]
    scheduled_at: datetime | None


class ExportQueueResponse(BaseModel):
    items: list[ExportItem]
