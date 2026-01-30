from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agents.image_generation_agent import ImageGenerationAgent
from integrations.openai_adapters import OpenAIImageGenerator, OpenAIJsonLLM
from pipeline.image_step import ensure_post_hero_is_present


POSTS_DIR = Path("site/src/content/posts")
PUBLIC_DIR = Path("site/public")
PUBLIC_IMAGES_DIR = Path("site/public/images")


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _extract_frontmatter(md: str) -> tuple[dict[str, Any], int, int]:
    m = FRONTMATTER_RE.search(md)
    if not m:
        return {}, -1, -1
    fm_raw = m.group(1)
    fm = yaml.safe_load(fm_raw) or {}
    return fm, m.start(0), m.end(0)


def _extract_section(md: str, heading: str) -> str:
    """
    Pull the body for a section like:
      ## Intro
      <body...>
      ## Next
    """
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^\s*##\s+|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    m = pattern.search(md)
    if not m:
        return ""
    return (m.group(1) or "").strip()


def _ensure_frontmatter_keys(md: str, updates: dict[str, str]) -> str:
    """
    If frontmatter exists, inject missing scalar keys after the first '---'.
    We do not rewrite YAML fully (keeps formatting stable).
    """
    fm, start, end = _extract_frontmatter(md)
    if start == -1:
        # No frontmatter; create one (rare in this repo)
        lines = ["---"]
        for k, v in updates.items():
            lines.append(f'{k}: "{v}"')
        lines.append("---\n")
        return "\n".join(lines) + md.lstrip()

    # Only inject missing keys
    missing_lines: list[str] = []
    for k, v in updates.items():
        if k not in fm:
            missing_lines.append(f'{k}: "{v}"')

    if not missing_lines:
        return md

    # Insert right after first '---\n'
    insert_at = start + 4  # len("---\n")
    return md[:insert_at] + "\n".join(missing_lines) + "\n" + md[insert_at:]


def _disk_path_from_public_url(url_path: str) -> Path:
    return PUBLIC_DIR / url_path.lstrip("/")


def _primary_category(fm: dict[str, Any]) -> str | None:
    cats = fm.get("categories")
    if isinstance(cats, list) and cats:
        return str(cats[0])
    cat = fm.get("category")
    if cat:
        return str(cat)
    return None


def main() -> int:
    if not POSTS_DIR.exists():
        raise FileNotFoundError(f"Missing posts dir: {POSTS_DIR}")

    llm = OpenAIJsonLLM()
    img = OpenAIImageGenerator()

    img_agent = ImageGenerationAgent(
        llm=llm,
        image_gen=img,
        public_images_dir=str(PUBLIC_IMAGES_DIR),
        posts_subdir="posts",
    )

    regenerated = 0
    skipped = 0
    updated_frontmatter = 0

    posts = sorted(POSTS_DIR.glob("*.md"))
    if not posts:
        print(f"⚠️ No posts found at {POSTS_DIR}")
        return 0

    for post_path in posts:
        slug = post_path.stem
        md = post_path.read_text(encoding="utf-8")

        fm, _, _ = _extract_frontmatter(md)

        title = str(fm.get("title") or slug)
        category = _primary_category(fm)

        intro = _extract_section(md, "Intro") or "A short, practical guide to the picks below."

        # Prefer picks bodies from frontmatter 'picks' (canonical in this engine)
        pick_snippets: list[str] = []
        picks = fm.get("picks")
        if isinstance(picks, list):
            for p in picks[:8]:
                if isinstance(p, dict):
                    body = (p.get("body") or "").strip()
                    if body:
                        pick_snippets.append(body[:240])

        # If no pick snippets exist, still allow a generic hero
        if not pick_snippets:
            pick_snippets = [title]

        # Determine intended hero path
        hero_url = fm.get("heroImage")
        if not isinstance(hero_url, str) or not hero_url.startswith("/images/posts/"):
            hero_url = f"/images/posts/{slug}/hero.webp"

        hero_disk = _disk_path_from_public_url(hero_url)

        if hero_disk.exists() and hero_disk.stat().st_size > 0:
            skipped += 1
            continue

        print(f"🖼️ Regenerating hero for: {slug}")
        hero = ensure_post_hero_is_present(
            agent=img_agent,
            public_dir=str(PUBLIC_DIR),
            slug=slug,
            category=category,
            title=title,
            intro=intro,
            picks=pick_snippets,
            alternatives=None,
        )

        regenerated += 1

        # If frontmatter lacks hero keys, inject them so future builds reference correct paths
        fm_updates: dict[str, str] = {}
        if not isinstance(fm.get("heroImage"), str):
            fm_updates["heroImage"] = hero.hero_image_path
        if not isinstance(fm.get("heroAlt"), str):
            fm_updates["heroAlt"] = hero.hero_alt

        # These are optional but nice to persist if absent
        if getattr(hero, "hero_image_home_path", None) and not isinstance(fm.get("heroImageHome"), str):
            fm_updates["heroImageHome"] = hero.hero_image_home_path  # type: ignore[assignment]
        if getattr(hero, "hero_image_card_path", None) and not isinstance(fm.get("heroImageCard"), str):
            fm_updates["heroImageCard"] = hero.hero_image_card_path  # type: ignore[assignment]
        if getattr(hero, "hero_source_path", None) and not isinstance(fm.get("heroImageSource"), str):
            fm_updates["heroImageSource"] = hero.hero_source_path  # type: ignore[assignment]

        if fm_updates:
            md2 = _ensure_frontmatter_keys(md, fm_updates)
            if md2 != md:
                post_path.write_text(md2, encoding="utf-8")
                updated_frontmatter += 1

    print("\n✅ Hero regen complete.")
    print(f"Regenerated: {regenerated}")
    print(f"Skipped (already OK): {skipped}")
    print(f"Frontmatter updated: {updated_frontmatter}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
