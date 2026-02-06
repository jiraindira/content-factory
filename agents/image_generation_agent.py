from __future__ import annotations

import os
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Protocol

from PIL import Image

from schemas.hero_image import HeroImageRequest, HeroImageResult


class JsonLLM(Protocol):
    def complete_json(self, *, system: str, user: str) -> dict: ...


class ImageGenerator(Protocol):
    def generate(self, *, prompt: str, fmt: str, width: int, height: int) -> bytes: ...


@dataclass(frozen=True)
class ImageStyle:
    id: str
    description: str


DEFAULT_STYLE = ImageStyle(
    id="editorial_minimal_v1",
    description=(
        "Minimal editorial illustration. Clean shapes, restrained palette, generous white space. "
        "No text, no logos, no brand marks, no photoreal product shots."
    ),
)


CATEGORY_ILLUSTRATION_STYLE = ImageStyle(
    id="category_illustration_v1",
    description=(
        "Playful, boutique lifestyle illustration in the same spirit as the site's category tiles: "
        "bold simplified shapes, slightly quirky proportions, warm modern palette, subtle paper/grain texture, "
        "clean background, light shadowing, and a cohesive scene. Not photorealistic. No text, no logos."
    ),
)


_STYLES_BY_ID: dict[str, ImageStyle] = {
    DEFAULT_STYLE.id: DEFAULT_STYLE,
    CATEGORY_ILLUSTRATION_STYLE.id: CATEGORY_ILLUSTRATION_STYLE,
}


@dataclass(frozen=True)
class HeroVariant:
    """A derived crop for a specific surface."""

    filename: str
    width: int
    height: int


class ImageGenerationAgent:
    """
    Wirecutter-aligned hero system:

    - Generate ONE canonical source image at 16:9.
    - Derive deterministic crops for different surfaces (no extra model calls).

    Output convention:
      - Disk: site/public/images/posts/<slug>/hero_source.webp
              site/public/images/posts/<slug>/hero.webp        (post)
              site/public/images/posts/<slug>/hero_home.webp   (homepage/featured)
              site/public/images/posts/<slug>/hero_card.webp   (cards)
      - URL:  /images/posts/<slug>/...
    """

    # Canonical (generate once)
    _SOURCE_W = 2000
    _SOURCE_H = 1125  # 16:9

    # Derived variants (deterministic)
    _VARIANTS = (
        HeroVariant("hero.webp", 1600, 900),
        # Home/featured surfaces render as 16:9 (`aspect-video`) across the site
        HeroVariant("hero_home.webp", 1200, 675),
        HeroVariant("hero_card.webp", 800, 600),
    )

    def __init__(
        self,
        *,
        llm: JsonLLM,
        image_gen: ImageGenerator,
        public_images_dir: str = "site/public/images",
        posts_subdir: str = "posts",
        style: ImageStyle = DEFAULT_STYLE,
    ) -> None:
        self._llm = llm
        self._image_gen = image_gen
        self._public_images_dir = Path(public_images_dir)
        self._posts_dir = self._public_images_dir / posts_subdir
        self._style = style

    def run(self, req: HeroImageRequest) -> HeroImageResult:
        self._validate_slug(req.slug)

        style = self._resolve_style(req)

        post_dir = self._posts_dir / req.slug
        post_dir.mkdir(parents=True, exist_ok=True)

        disk_source = post_dir / "hero_source.webp"
        disk_post = post_dir / "hero.webp"
        disk_home = post_dir / "hero_home.webp"
        disk_card = post_dir / "hero_card.webp"

        pub_source = f"/images/posts/{req.slug}/hero_source.webp"
        pub_post = f"/images/posts/{req.slug}/hero.webp"
        pub_home = f"/images/posts/{req.slug}/hero_home.webp"
        pub_card = f"/images/posts/{req.slug}/hero_card.webp"

        # If post hero exists, consider the set done. We still backfill missing variants if needed.
        if disk_post.exists() and disk_post.stat().st_size > 0:
            if disk_source.exists() and disk_source.stat().st_size > 0:
                try:
                    self._ensure_variants_from_source(disk_source, post_dir)
                except Exception:
                    pass

            return HeroImageResult(
                hero_image_path=pub_post,
                hero_image_home_path=pub_home if disk_home.exists() else None,
                hero_image_card_path=pub_card if disk_card.exists() else None,
                hero_source_path=pub_source if disk_source.exists() else None,
                hero_alt=self._default_alt(req),
                hero_prompt="(existing files; prompt not regenerated)",
                style_id=style.id,
            )

        prompt, alt = self._create_prompt_and_alt(req, style=style)

        # 1) Generate canonical 16:9
        src_bytes = self._image_gen.generate(
            prompt=prompt,
            fmt="webp",
            width=self._SOURCE_W,
            height=self._SOURCE_H,
        )
        self._atomic_write(disk_source, src_bytes)

        # 2) Derive crops for surfaces (no extra model calls)
        self._write_variants_from_bytes(post_dir, src_bytes)

        return HeroImageResult(
            hero_image_path=pub_post,
            hero_image_home_path=pub_home,
            hero_image_card_path=pub_card,
            hero_source_path=pub_source,
            hero_alt=alt,
            hero_prompt=prompt,
            style_id=style.id,
        )

    # ----------------------------
    # Prompting
    # ----------------------------

    def _create_prompt_and_alt(self, req: HeroImageRequest, *, style: ImageStyle) -> tuple[str, str]:
        nouns = self._extract_concrete_nouns(req)
        nouns_line = ", ".join(nouns[:8]) if nouns else "general everyday objects"

        composition_rules = (
            "Composition/format rules (non-negotiable):\n"
            "- Aspect ratio must be 16:9 (editorial hero).\n"
            "- IMPORTANT: This 16:9 source will be center-cropped to other surfaces (notably 4:3 cards).\n"
            "- Keep the primary subject fully inside a conservative safe area (middle ~60% width AND ~70% height).\n"
            "- Avoid critical details near the left/right edges (they may be cropped in 4:3).\n"
            "- Leave generous negative space; backgrounds should tolerate cropping.\n"
            "- No text, no labels, no UI elements.\n"
            "- No logos, trademarks, or brand identifiers.\n"
            "- Not photorealistic product photography.\n"
        )

        system = (
            "You are an editorial art director. Create a SINGLE prompt for a blog hero image.\n"
            + composition_rules
            + "Return JSON with keys: prompt (string), alt (string).\n"
            "The prompt must describe one cohesive illustration scene matching the topic.\n"
        )

        user = (
            f"STYLE:\n{style.description}\n\n"
            "POST CONTEXT:\n"
            f"- slug: {req.slug}\n"
            f"- category: {req.category or 'n/a'}\n"
            f"- title (optional): {req.title or 'n/a'}\n\n"
            "TEXT EXCERPTS:\n"
            f"INTRO:\n{req.intro}\n\n"
            "PICKS (snippets):\n"
            + "\n".join(f"- {p[:240]}" for p in req.picks[:8])
            + ("\n\nALTERNATIVES:\n" + req.alternatives[:400] if req.alternatives else "")
            + "\n\n"
            f"CONCRETE NOUN HINTS (not brands): {nouns_line}\n\n"
            "Make the prompt describe one cohesive illustration scene that matches the topic.\n"
            "Do not include any brand names. Do not include the word 'Amazon'.\n"
        )

        data = self._llm.complete_json(system=system, user=user)
        prompt = str(data.get("prompt", "")).strip()
        alt = str(data.get("alt", "")).strip()

        if not prompt:
            prompt = (
                f"{style.description} "
                "Create a 16:9 editorial hero illustration representing the theme of the post. "
                "Use simple shapes and ample white space. "
                "Keep the main subject within the central safe area. "
                "No text, no logos, not photorealistic."
            )

        if not alt:
            alt = self._default_alt(req)

        prompt = self._scrub_brands(prompt)
        alt = self._scrub_brands(alt)

        if "16:9" not in prompt:
            prompt = (prompt + " Render as a 16:9 editorial hero image.").strip()

        return prompt, alt

    def _resolve_style(self, req: HeroImageRequest) -> ImageStyle:
        style_id = (getattr(req, "style_id", None) or "").strip()
        if not style_id:
            return self._style
        return _STYLES_BY_ID.get(style_id, self._style)

    # ----------------------------
    # Image derivation
    # ----------------------------

    def ensure_variants_from_source(self, disk_source: Path, post_dir: Path) -> None:
        """Regenerate derived hero variants from an existing canonical source image.

        This does not call the image model; it only crops/resizes deterministically.
        """
        self._ensure_variants_from_source(disk_source, post_dir)

    def _ensure_variants_from_source(self, disk_source: Path, post_dir: Path) -> None:
        src_bytes = disk_source.read_bytes()
        self._write_variants_from_bytes(post_dir, src_bytes)

    def _write_variants_from_bytes(self, post_dir: Path, src_bytes: bytes) -> None:
        for v in self._VARIANTS:
            out_path = post_dir / v.filename
            if out_path.exists() and out_path.stat().st_size > 0:
                try:
                    with Image.open(out_path) as existing:
                        if existing.size == (v.width, v.height):
                            continue
                except Exception:
                    # If the file can't be opened/validated, regenerate it.
                    pass
            derived = self._crop_resize(src_bytes, target_w=v.width, target_h=v.height)
            self._atomic_write(out_path, derived)

    def _crop_resize(self, src_bytes: bytes, *, target_w: int, target_h: int) -> bytes:
        with Image.open(BytesIO(src_bytes)) as im:
            im = im.convert("RGB")

            src_w, src_h = im.size
            target_ar = target_w / target_h
            src_ar = src_w / src_h

            # Center crop to target aspect ratio
            if abs(src_ar - target_ar) > 1e-6:
                if src_ar > target_ar:
                    new_w = int(round(src_h * target_ar))
                    new_h = src_h
                    left = (src_w - new_w) // 2
                    top = 0
                else:
                    new_w = src_w
                    new_h = int(round(src_w / target_ar))
                    left = 0
                    top = (src_h - new_h) // 2
                right = left + new_w
                bottom = top + new_h
                im = im.crop((left, top, right, bottom))

            im = im.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)

            out = BytesIO()
            im.save(out, format="WEBP", quality=92, method=6)
            return out.getvalue()

    # ----------------------------
    # Helpers
    # ----------------------------

    def _default_alt(self, req: HeroImageRequest) -> str:
        if req.category:
            return f"Editorial illustration for a {req.category} buying guide."
        return "Editorial illustration for a buying guide."

    def _extract_concrete_nouns(self, req: HeroImageRequest) -> list[str]:
        text = " ".join([req.intro, *req.picks, req.alternatives or ""])
        text = re.sub(r"[^A-Za-z0-9\\s]", " ", text).lower()

        stop = {
            "this",
            "that",
            "these",
            "those",
            "with",
            "your",
            "you",
            "and",
            "the",
            "for",
            "from",
            "into",
            "over",
            "under",
            "when",
            "what",
            "which",
            "while",
            "their",
            "they",
            "them",
            "about",
            "because",
            "just",
            "very",
            "more",
            "most",
            "less",
            "best",
            "top",
            "great",
            "good",
            "nice",
            "easy",
            "hard",
            "does",
            "will",
            "can",
            "could",
            "should",
            "would",
            "guide",
            "buying",
            "picks",
            "alternatives",
            "chosen",
            "list",
        }

        tokens = [
            t for t in text.split() if 4 <= len(t) <= 18 and t not in stop and not t.isdigit()
        ]

        freq: dict[str, int] = {}
        for t in tokens:
            freq[t] = freq.get(t, 0) + 1

        ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
        return [w for (w, c) in ranked if c >= 2][:20] or [w for (w, _) in ranked[:12]]

    def _scrub_brands(self, s: str) -> str:
        banned = ["amazon", "nike", "adidas", "sony", "apple", "samsung", "gopro"]
        out = s
        for b in banned:
            out = re.sub(rf"\\b{re.escape(b)}\\b", "", out, flags=re.IGNORECASE)
        return re.sub(r"\\s{2,}", " ", out).strip()

    def _validate_slug(self, slug: str) -> None:
        if not slug or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValueError(f"Invalid slug '{slug}'. Expected lowercase kebab-case.")

    def _atomic_write(self, path: Path, data: bytes) -> None:
        tmp = Path(str(path) + ".tmp")
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
