import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict

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


class CandidatePromptOut(BaseModel):
    """`GET /candidates/{id}/prompt`。Generator AgentがLLMへ送るのと同一の本文。"""

    candidate_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    prompt_version: str
    prompt: str


class ManualContentRequest(BaseModel):
    """チャットUIが返したJSONをそのまま貼り付ける想定。

    コードフェンス付きのまま貼られる場合があるため、本文は生文字列で受けて
    `app.agents.manual_content.parse_manual_content` 側で剥がす。
    """

    model_config = ConfigDict(extra="forbid")

    content: str
    prompt_version: str | None = None


class ManualContentOut(BaseModel):
    content_id: uuid.UUID
    candidate_id: uuid.UUID
    status: str
    generation_source: str
    prompt_version: str
    rule_violations: list[str]
