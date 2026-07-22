from pydantic import BaseModel


class PageMeta(BaseModel):
    page: int
    per_page: int
    total: int
