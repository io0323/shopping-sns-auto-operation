from typing import Any

from pydantic import BaseModel

from app.schemas.prompt import PromptVersionOut


class LearningReportOut(BaseModel):
    run_date: str | None
    status: str
    data_point_count: int | None
    report: dict[str, Any] | None
    proposed_prompt_version: PromptVersionOut | None
