import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pipeline: str
    step: str
    status: str
    payload: dict[str, Any] | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
