from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agents.image_generation_agent import ImageGenerationAgent
from pipeline.hero_self_heal import ensure_hero_assets_exist


@dataclass(frozen=True)
class HeroImageResult:
    hero_image_path: str
    hero_alt: str
    hero_image_home_path: Optional[str] = None
    hero_image_card_path: Optional[str] = None
    hero_source_path: Optional[str] = None


def generate_hero_image(
    *,
    agent: ImageGenerationAgent,
    slug: str,
    category: str | None,
    title: str,
    intro: str,
    picks: list[str],
    alternatives: str | None,
) -> HeroImageResult:
    """
    Generate hero images for a post slug.

    This should be the "happy path" generation. If it raises, the caller may self-heal.
    """
    req = {
        "slug": slug,
        "category": category,
        "title": title,
        "intro": intro,
        "picks": picks,
        "alternatives": alternatives,
    }

    out = agent.run(req)

    # Keep compatibility with whatever ImageGenerationAgent returns.
    # We assume these attributes exist based on earlier pipeline usage.
    return HeroImageResult(
        hero_image_path=out.hero_image_path,
        hero_alt=out.hero_alt,
        hero_image_home_path=getattr(out, "hero_image_home_path", None),
        hero_image_card_path=getattr(out, "hero_image_card_path", None),
        hero_source_path=getattr(out, "hero_source_path", None),
    )


def ensure_post_hero_is_present(
    *,
    agent: ImageGenerationAgent,
    public_dir: str,
    slug: str,
    category: str | None,
    title: str,
    intro: str,
    picks: list[str],
    alternatives: str | None,
    placeholder_url: str = "/images/placeholder-hero.webp",
) -> HeroImageResult:
    """
    Self-healing wrapper:
    - Guarantees hero files exist on disk for the slug (either generated or placeholder copied).
    - Returns canonical hero paths for frontmatter.
    """
    from pathlib import Path

    public_dir_path = Path(public_dir)

    # attempt regen; on failure copy placeholder into the canonical hero paths
    ensure_hero_assets_exist(
        public_dir=public_dir_path,
        slug=slug,
        placeholder_url=placeholder_url,
        regen_fn=generate_hero_image,
        regen_kwargs={
            "agent": agent,
            "slug": slug,
            "category": category,
            "title": title,
            "intro": intro,
            "picks": picks,
            "alternatives": alternatives,
        },
    )

    # Return canonical paths used by the site (even if placeholder was copied)
    # This is what your posts already reference.
    base = f"/images/posts/{slug}"
    return HeroImageResult(
        hero_image_path=f"{base}/hero.webp",
        hero_alt=f"{title} hero image",
        hero_image_home_path=f"{base}/hero_home.webp",
        hero_image_card_path=f"{base}/hero_card.webp",
        hero_source_path=f"{base}/hero_source.webp",
    )
