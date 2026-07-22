from datetime import date

from pydantic import BaseModel


class GenreKpi(BaseModel):
    genre_id: str
    genre_name: str
    clicks: int
    conversions: int
    revenue: int


class AnalyticsSummary(BaseModel):
    date_from: date | None
    date_to: date | None
    clicks: int
    conversions: int
    revenue: int
    by_genre: list[GenreKpi]
