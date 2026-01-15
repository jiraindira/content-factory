from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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


class ImageGenerationAgent:
    """
    Generates ONE hero image per post (first creation only).

    Output convention (matches your current repo conventions):
      - Disk: site/public/images/posts/<slug>/hero.webp
      - URL:  /images/posts/<slug>/hero.webp
    """

    def __init__(
        self,
        *,
        llm: JsonLLM,
        image_gen: ImageGenerator,
        public_images_dir: str = "site/public/images",
        posts_subdir: str = "posts",
        width: int = 1400,
        height: int = 800,
        style: ImageStyle = DEFAULT_STYLE,
    ) -> None:
        self._llm = llm
        self._image_gen = image_gen
        self._public_images_dir = Path(public_images_dir)
        self._posts_dir = self._public_images_dir / posts_subdir
        self._width = width
        self._height = height
        self._style = style

    def run(self, req: HeroImageRequest) -> HeroImageResult:
        self._validate_slug(req.slug)

        post_dir = self._posts_dir / req.slug
        post_dir.mkdir(parents=True, exist_ok=True)

        disk_path = post_dir / "hero.webp"
        public_path = f"/images/posts/{req.slug}/hero.webp"

        # First-creation rule: do nothing if it already exists
        if disk_path.exists() and disk_path.stat().st_size > 0:
            return HeroImageResult(
                hero_image_path=public_path,
                hero_alt=self._default_alt(req),
                hero_prompt="(existing file; prompt not regenerated)",
                style_id=self._style.id,
            )

        prompt, alt = self._create_prompt_and_alt(req)

        img_bytes = self._image_gen.generate(
            prompt=prompt,
            fmt="webp",
            width=self._width,
            height=self._height,
        )

        self._atomic_write(disk_path, img_bytes)

        return HeroImageResult(
            hero_image_path=public_path,
            hero_alt=alt,
            hero_prompt=prompt,
            style_id=self._style.id,
        )

    def _create_prompt_and_alt(self, req: HeroImageRequest) -> tuple[str, str]:
        nouns = self._extract_concrete_nouns(req)
        nouns_line = ", ".join(nouns[:8]) if nouns else "general everyday objects"

        system = (
            "You are an editorial art director. Create a SINGLE prompt for a hero image.\n"
            "Hard rules:\n"
            "- No text in the image.\n"
            "- No logos, trademarks, or brand identifiers.\n"
            "- Avoid photorealistic product photography.\n"
            "- Prefer simple, metaphorical editorial illustration.\n"
            "- Keep it clean and modern.\n"
            "Return JSON with keys: prompt (string), alt (string).\n"
        )

        user = (
            f"STYLE:\n{self._style.description}\n\n"
            f"POST CONTEXT:\n"
            f"- slug: {req.slug}\n"
            f"- category: {req.category or 'n/a'}\n"
            f"- title (optional): {req.title or 'n/a'}\n\n"
            f"TEXT EXCERPTS:\n"
            f"INTRO:\n{req.intro}\n\n"
            f"PICKS (snippets):\n"
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
                f"{self._style.description} "
                "Create an abstract editorial illustration representing the theme of the post. "
                "Use simple shapes and ample white space. No text, no logos."
            )

        if not alt:
            alt = self._default_alt(req)

        prompt = self._scrub_brands(prompt)
        alt = self._scrub_brands(alt)

        return prompt, alt

    def _default_alt(self, req: HeroImageRequest) -> str:
        if req.category:
            return f"Editorial illustration for a {req.category} buying guide."
        return "Editorial illustration for a buying guide."

    def _extract_concrete_nouns(self, req: HeroImageRequest) -> list[str]:
        text = " ".join([req.intro, *req.picks, req.alternatives or ""])
        text = re.sub(r"[^A-Za-z0-9\s]", " ", text).lower()

        stop = {
            "this", "that", "these", "those", "with", "your", "you", "and", "the", "for", "from",
            "into", "over", "under", "when", "what", "which", "while", "their", "they", "them",
            "about", "because", "just", "very", "more", "most", "less", "best", "top", "great",
            "good", "nice", "easy", "hard", "does", "will", "can", "could", "should", "would",
            "guide", "buying", "picks", "alternatives", "chosen", "list"
        }

        tokens = [t for t in text.split() if 4 <= len(t) <= 18 and t not in stop and not t.isdigit()]

        freq: dict[str, int] = {}
        for t in tokens:
            freq[t] = freq.get(t, 0) + 1

        ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
        return [w for (w, c) in ranked if c >= 2][:20] or [w for (w, _) in ranked[:12]]

    def _scrub_brands(self, s: str) -> str:
        banned = ["amazon", "nike", "adidas", "sony", "apple", "samsung", "gopro"]
        out = s
        for b in banned:
            out = re.sub(rf"\b{re.escape(b)}\b", "", out, flags=re.IGNORECASE)
        return re.sub(r"\s{2,}", " ", out).strip()

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
