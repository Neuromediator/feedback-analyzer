"""Pydantic models shared by the API, runner and database layers."""

from typing import Literal

from pydantic import BaseModel, Field

Sentiment = Literal["negative", "neutral", "positive"]


class ReviewIn(BaseModel):
    id: int
    text: str


class RawResult(BaseModel):
    """One analyzer answer for one review."""

    id: int
    score: int = Field(ge=1, le=5)
    theme: str
    model: str = ""


class ReviewResult(BaseModel):
    id: int
    text: str
    status: Literal["pending", "ok", "failed"] = "pending"
    score: int | None = None
    sentiment: Sentiment | None = None
    theme: str | None = None
    suggestion: str | None = None
    model: str | None = None


class Summary(BaseModel):
    total: int
    average_score: float | None
    percent_positive: int | None
    top_theme: str | None
    top_complaint_theme: str | None
    theme_counts: dict[str, int]


class JobOut(BaseModel):
    id: str
    status: Literal["running", "done", "error"]
    stage: Literal["analyzing", "suggesting", "finished"]
    total: int
    done: int
    failed: int
    duplicates_removed: int
    error: str | None
    results: list[ReviewResult]
    summary: Summary


class JobCreate(BaseModel):
    reviews: list[str]


class SaveItem(BaseModel):
    text: str
    score: int = Field(ge=1, le=5)
    sentiment: Sentiment
    theme: str
    suggestion: str | None = None
    model: str


class SaveIn(BaseModel):
    items: list[SaveItem]


class SavedReview(SaveItem):
    id: int
    created_at: str


class ThemeIn(BaseModel):
    name: str
