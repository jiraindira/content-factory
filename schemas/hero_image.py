from __future__ import annotations

from pydantic import BaseModel, Field


class HeroImageRequest(BaseModel):
    slug: str = Field(..., description="Post slug (folder name) for deterministic output paths.")
    category: str | None = Field(None, description="Optional taxonomy category.")
    title: str | None = Field(None, description="Optional current title.")
    style_id: str | None = Field(
        None,
        description=(
            "Optional override for the image house style (e.g. 'editorial_minimal_v1'). "
            "If omitted, the agent uses its default style."
        ),
    )
    intro: str = Field(..., description="Rendered intro paragraph(s).")
    picks: list[str] = Field(default_factory=list, description="Rendered pick blurbs (one per product).")
    alternatives: str | None = Field(None, description="Rendered alternatives section (bullets as text).")


class HeroImageResult(BaseModel):
    hero_image_path: str = Field(..., description="Public path, e.g. /images/posts/<slug>/hero.webp")
    hero_image_home_path: str | None = Field(
        None,
        description="Optional public path for homepage/featured surfaces, e.g. /images/posts/<slug>/hero_home.webp",
    )
    hero_image_card_path: str | None = Field(
        None,
        description="Optional public path for small cards, e.g. /images/posts/<slug>/hero_card.webp",
    )
    hero_source_path: str | None = Field(
        None,
        description="Optional public path for the canonical source image, e.g. /images/posts/<slug>/hero_source.webp",
    )
    hero_alt: str = Field(..., description="Alt text for accessibility.")
    hero_prompt: str = Field(..., description="Prompt used (for repro/debug).")
    style_id: str = Field(..., description="Identifier for the house style.")
