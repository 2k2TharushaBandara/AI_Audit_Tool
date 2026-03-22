from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class FetchResult(BaseModel):
    requested_url: str
    final_url: str
    status_code: int
    fetched_at: datetime
    content_type: str | None = None
    html: str
    blocked_reason: str | None = None


class LinkCounts(BaseModel):
    internal: int = 0
    external: int = 0
    other: int = 0


class HeadingCounts(BaseModel):
    h1: int = 0
    h2: int = 0
    h3: int = 0


class ImageAltStats(BaseModel):
    total_images: int = 0
    missing_alt: int = 0
    missing_alt_pct: float = 0.0


class CountedImageItem(BaseModel):
    src: str | None = None
    alt: str | None = None
    counted_missing_alt: bool


class PageMetrics(BaseModel):
    # Assignment-required total word count.
    word_count: int
    counted_words: list[str] = Field(default_factory=list)
    headings: HeadingCounts
    heading_texts: dict[str, list[str]] = Field(default_factory=dict)
    cta_count: int
    counted_cta_texts: list[str] = Field(default_factory=list)
    links: LinkCounts
    counted_internal_links: list[str] = Field(default_factory=list)
    counted_external_links: list[str] = Field(default_factory=list)
    counted_other_links: list[str] = Field(default_factory=list)
    images: ImageAltStats
    counted_images: list[CountedImageItem] = Field(default_factory=list)
    meta_title: str | None = None
    meta_description: str | None = None

    # Small samples used to ground AI; still deterministic.
    sample_headings: list[str] = Field(default_factory=list)
    sample_cta_texts: list[str] = Field(default_factory=list)
    text_sample: str = ""


InsightKey = Literal[
    "seo_structure",
    "messaging_clarity",
    "cta_usage",
    "content_depth",
    "ux_structural_concerns",
]


class InsightItem(BaseModel):
    title: str
    evidence: list[str] = Field(default_factory=list)
    why_it_matters: str


class Recommendation(BaseModel):
    priority: int = Field(ge=1, le=5)
    title: str
    reasoning: str
    actions: list[str] = Field(default_factory=list)
    metric_references: list[str] = Field(default_factory=list)


class AiReport(BaseModel):
    summary: str
    insights: dict[InsightKey, list[InsightItem]]
    recommendations: list[Recommendation]


class PromptLog(BaseModel):
    id: str
    created_at: datetime
    model: str
    system_prompt: str
    user_prompt: str
    structured_input: dict[str, Any]
    raw_model_output: str
    parsed_output: dict[str, Any] | None = None
    error: str | None = None
