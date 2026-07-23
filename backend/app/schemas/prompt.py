import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PromptVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent: str
    version: str
    body: str
    is_active: bool
    note: str | None
    created_at: datetime


class PromptActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_version_id: uuid.UUID
