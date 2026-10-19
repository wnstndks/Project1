from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    published_at: datetime
    source: str
    headline: str
    url: str
    positive: float
    negative: float
    neutral: float


class NewsDayOut(BaseModel):
    date: date
    tone: float | None
    volume: int | None


class NewsOut(BaseModel):
    symbol: str
    articles: list[ArticleOut]
    days: list[NewsDayOut]
    finnhub_enabled: bool
