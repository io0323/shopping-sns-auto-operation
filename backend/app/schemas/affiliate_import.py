from pydantic import BaseModel


class ImportErrorOut(BaseModel):
    raw_line: str
    reason: str


class ImportSummary(BaseModel):
    imported: int
    updated: int
    error_count: int
    errors: list[ImportErrorOut]
