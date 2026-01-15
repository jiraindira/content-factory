from __future__ import annotations

from agents.image_generation_agent import ImageGenerationAgent
from schemas.hero_image import HeroImageRequest, HeroImageResult


def generate_hero_image(
    *,
    agent: ImageGenerationAgent,
    slug: str,
    category: str | None,
    title: str | None,
    intro: str,
    picks: list[str],
    alternatives: str | None,
) -> HeroImageResult:
    req = HeroImageRequest(
        slug=slug,
        category=category,
        title=title,
        intro=intro,
        picks=picks,
        alternatives=alternatives,
    )
    return agent.run(req)
