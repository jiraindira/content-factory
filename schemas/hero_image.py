from __future__ import annotations

from pydantic import BaseModel, Field


class HeroImageRequest(BaseModel):
    slug: str = Field(..., description="Post slug (folder name) for deterministic output paths.")
    category: str | None = Field(None, description="Optional taxonomy category.")
    title: str | None = Field(None, description="Optional current title.")
    intro: str = Field(..., description="Rendered intro paragraph(s).")
    picks: list[str] = Field(default_factory=list, description="Rendered pick blurbs (one per product).")
    alternatives: str | None = Field(None, description="Rendered alternatives section (bullets as text).")


class HeroImageResult(BaseModel):
    hero_image_path: str = Field(..., description="Public path, e.g. /images/posts/<slug>/hero.webp")
    hero_alt: str = Field(..., description="Alt text for accessibility.")
    hero_prompt: str = Field(..., description="Prompt used (for repro/debug).")
    style_id: str = Field(..., description="Identifier for the house style.")
