from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.depth_expansion_agent import DepthExpansionAgent
from agents.final_title_agent import FinalTitleAgent, FinalTitleConfig
from agents.image_generation_agent import ImageGenerationAgent
from agents.preflight_qa_agent import PreflightQAAgent
from agents.post_repair_agent import PostRepairAgent, PostRepairConfig

from integrations.openai_adapters import OpenAIJsonLLM, OpenAIImageGenerator
from pipeline.image_step import generate_hero_image

from lib.product_catalog import ProductCatalog
from lib.post_formats import get_format_spec
from lib.markdown_normalizer import normalize_markdown
from schemas.depth import DepthExpansionInput, ExpansionModuleSpec
from schemas.post_format import PostFormatId


ASTRO_POSTS_DIR = Path("site/src/content/posts")
PUBLIC_IMAGES_DIR = Path("site/public/images")
CATALOG_PATH = Path("data/catalog/master.json")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(text: str) -> str:
    s = (text or "").lower().strip()
    s = s.replace("’", "").replace("'", "")
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


_H2_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")
_PICK_ID_COMMENT_RE = re.compile(r"(?m)^\s*<!--\s*pick_id:\s*([a-z0-9\-_:]+)\s*-->\s*$", re.I)
_H3_RE = re.compile(r"(?m)^\s*###\s+(.+?)\s*$")


def _extract_section(md: str, heading: str) -> str:
    """
    Extract the markdown content under `## {heading}` until next H2.
    Returns body (no heading line).
    """
    text = md or ""
    lines = text.splitlines()

    start_idx = None
    for i, ln in enumerate(lines):
        m = _H2_RE.match(ln)
        if m and m.group(1).strip().lower() == heading.strip().lower():
            start_idx = i + 1
            break
    if start_idx is None:
        return ""

    end_idx = len(lines)
    for j in range(start_idx, len(lines)):
        m = _H2_RE.match(lines[j])
        if m:
            end_idx = j
            break

    body = "\n".join(lines[start_idx:end_idx]).strip()
    return body


def _extract_pick_bodies(md: str) -> dict[str, str]:
    """
    Parse bodies inside the '## The picks' section.

    Expected structure per pick:
      <!-- pick_id: X -->
      ### Title
      <body...>
      <hr />

    Returns: { pick_id -> body_markdown }
    """
    text = md or ""
    lines = text.splitlines()

    # Find "## The picks"
    start = None
    for i, ln in enumerate(lines):
        m = _H2_RE.match(ln)
        if m and m.group(1).strip().lower() == "the picks":
            start = i + 1
            break
    if start is None:
        return {}

    # End at next H2
    end = len(lines)
    for j in range(start, len(lines)):
        if j == start:
            continue
        if _H2_RE.match(lines[j]):
            end = j
            break

    picks_lines = lines[start:end]

    out: dict[str, str] = {}
    i = 0
    while i < len(picks_lines):
        m = _PICK_ID_COMMENT_RE.match(picks_lines[i])
        if not m:
            i += 1
            continue

        pick_id = m.group(1).strip()

        # Advance to next non-empty line, expect H3, then body starts after it
        k = i + 1
        while k < len(picks_lines) and picks_lines[k].strip() == "":
            k += 1
        if k >= len(picks_lines):
            break

        h3 = _H3_RE.match(picks_lines[k])
        if not h3:
            # If the structure is broken, skip this pick deterministically
            i = k + 1
            continue

        body_start = k + 1

        # Body ends at next <hr /> or next pick marker
        body_end = len(picks_lines)
        for t in range(body_start, len(picks_lines)):
            if picks_lines[t].strip().lower().startswith("<hr"):
                body_end = t
                break
            if _PICK_ID_COMMENT_RE.match(picks_lines[t]):
                body_end = t
                break

        body = "\n".join(picks_lines[body_start:body_end]).strip()
        out[pick_id] = body

        i = body_end + 1

    return out


class ManualPostWriter:
    def __init__(self, logger=print) -> None:
        self._log = logger

    def run(
        self,
        *,
        input_path: str,
        post_date: str,
        dry_run: bool = False,
        debug_dir: str | None = None,
    ) -> int:
        input_path_p = Path(input_path)
        if not input_path_p.exists():
            raise FileNotFoundError(f"Missing input file: {input_path_p}")

        raw = json.loads(input_path_p.read_text(encoding="utf-8"))

        category = raw.get("category", "general")
        subcategory = raw.get("subcategory")
        audience = raw.get("audience", "UK readers")
        raw_products = raw.get("products", [])

        if len(raw_products) < 3:
            raise RuntimeError("post_input.json must contain at least 3 products")

        # Normalize products
        products: list[dict[str, Any]] = []
        for p in raw_products:
            title = p.get("title") or p.get("name")
            if not title:
                raise RuntimeError("Each product must have 'title' (or 'name')")

            url = str(p.get("url", "")).strip()
            if not url:
                raise RuntimeError("Each product must have a non-empty 'url' (schema requires a valid URL).")

            products.append(
                {
                    "title": str(title).strip(),
                    "url": url,
                    "price": str(p.get("price", "—")).strip() or "—",
                    "rating": float(p.get("rating", 0) or 0),
                    "reviews_count": int(p.get("reviews_count", 0) or 0),
                    "description": str(p.get("description", "")).strip(),
                    "catalog_key": p.get("catalog_key"),
                }
            )

        # Title + slug
        llm = OpenAIJsonLLM()
        title_agent = FinalTitleAgent(llm=llm, config=FinalTitleConfig(max_chars=60))
        title = title_agent.run(
            topic=subcategory or category,
            category=category,
            intro="",
            picks=[],
            products=products,
            alternatives=None,
        )

        slug = f"{post_date}-{_slugify(title)}"
        self._log(f"🟢 Writing post: {slug}")

        # Catalog upsert
        catalog = ProductCatalog(path=CATALOG_PATH)
        catalog.ensure_entries_for_products(provider="amazon_uk", products=products)

        # Astro frontmatter products array
        astro_products: list[dict[str, Any]] = []
        for idx, p in enumerate(products, start=1):
            astro_products.append(
                {
                    "pick_id": f"pick-{idx}-{_slugify(p['title'])}",
                    "catalog_key": p.get("catalog_key"),
                    "title": p["title"],
                    "url": p["url"],
                    "price": p["price"],
                    "rating": p["rating"],
                    "reviews_count": p["reviews_count"],
                    "description": p["description"],
                }
            )

        product_titles = [p["title"] for p in astro_products if isinstance(p.get("title"), str)]

        format_id: PostFormatId = "top_picks"
        format_spec = get_format_spec(format_id)

        # Draft scaffold (includes picks placeholders so DepthExpansion can author them)
        md = [
            "---",
            f'title: "{title}"',
            f'description: "Curated {category.replace("_"," ")} picks for {audience}."',
            f'publishedAt: "{_utc_now_iso()}"',
            f'category: "{category}"',
            f'audience: "{audience}"',
            f"products: {json.dumps(astro_products, ensure_ascii=False)}",
            "---",
            "",
            "## Intro",
            "",
            "{{INTRO}}",
            "",
            "## How this list was chosen",
            "",
            "{{HOW_WE_CHOSE}}",
            "",
            "## The picks",
            "",
        ]

        for p in astro_products:
            md.extend(
                [
                    f"<!-- pick_id: {p['pick_id']} -->",
                    f"### {p['title']}",
                    "",
                    f"{{{{PICK:{p['pick_id']}}}}}",
                    "",
                    "<hr />",
                    "",
                ]
            )

        draft_markdown = "\n".join(md)

        # Content generation
        depth_agent = DepthExpansionAgent()
        modules = [
            ExpansionModuleSpec(name="intro", enabled=True, max_words=format_spec.max_words_intro, rewrite_mode="upgrade"),
            ExpansionModuleSpec(
                name="how_we_chose",
                enabled=True,
                max_words=format_spec.max_words_how_we_chose,
                rewrite_mode="upgrade",
            ),
            ExpansionModuleSpec(
                name="product_writeups",
                enabled=True,
                max_words=format_spec.max_words_product_writeups,
                rewrite_mode="upgrade",
            ),
        ]

        depth_out = depth_agent.run(
            DepthExpansionInput(
                draft_markdown=draft_markdown,
                products=astro_products,
                modules=modules,
                rewrite_mode="upgrade",
                max_added_words=sum(m.max_words for m in modules),
                voice="neutral",
                faqs=[],
                forbid_claims_of_testing=True,
            )
        )

        expanded_markdown = depth_out.get("expanded_markdown", draft_markdown)

        # Deterministic structural normalization (makes parsing safe)
        expanded_markdown = normalize_markdown(expanded_markdown, product_titles=product_titles)

        # Extract authored content
        intro_body = _extract_section(expanded_markdown, "Intro")
        how_body = _extract_section(expanded_markdown, "How this list was chosen")
        pick_bodies = _extract_pick_bodies(expanded_markdown)

        # Build structured picks array aligned to products order
        picks_structured = []
        for p in astro_products:
            pid = p["pick_id"]
            picks_structured.append({"pick_id": pid, "body": pick_bodies.get(pid, "").strip()})

        # Minimal markdown body: Intro + How only
        final_md_lines = [
            "---",
            f'title: "{title}"',
            f'description: "Curated {category.replace("_"," ")} picks for {audience}."',
            f'publishedAt: "{_utc_now_iso()}"',
            f'category: "{category}"',
            f'audience: "{audience}"',
            f"products: {json.dumps(astro_products, ensure_ascii=False)}",
            f"picks: {json.dumps(picks_structured, ensure_ascii=False)}",
            "---",
            "",
            "## Intro",
            "",
            intro_body.strip() if intro_body.strip() else "A short, practical guide to the picks below.",
            "",
            "## How this list was chosen",
            "",
            how_body.strip() if how_body.strip() else "Everything here was chosen to be practical and easy to use.",
            "",
        ]
        final_markdown = "\n".join(final_md_lines).strip() + "\n"

        # Hero image
        try:
            img_agent = ImageGenerationAgent(
                llm=llm,
                image_gen=OpenAIImageGenerator(),
                public_images_dir=str(PUBLIC_IMAGES_DIR),
                posts_subdir="posts",
                width=1400,
                height=800,
            )
            hero = generate_hero_image(
                agent=img_agent,
                slug=slug,
                category=category,
                title=title,
                intro=intro_body,
                picks=[],
                alternatives=None,
            )
            final_markdown = final_markdown.replace(
                "---",
                f'---\nheroImage: "{hero.hero_image_path}"\nheroAlt: "{hero.hero_alt}"',
                1,
            )
        except Exception:
            pass

        # QA + repair (non-blocking)
        qa = PreflightQAAgent(strict=False)
        report = qa.run(
            final_markdown=final_markdown,
            frontmatter={},
            intro_text=intro_body,
            picks_texts=[p.get("body", "") for p in picks_structured],
            products=astro_products,
        )

        if not report.ok:
            try:
                repair = PostRepairAgent(llm=llm, config=PostRepairConfig(max_changes=12))
                repaired = repair.run(
                    draft_markdown=final_markdown,
                    qa_report=report.model_dump(),
                    products=astro_products,
                    intro_text=intro_body,
                    picks_texts=[p.get("body", "") for p in picks_structured],
                )
                if isinstance(repaired, dict):
                    final_markdown = repaired.get("repaired_markdown", final_markdown)
            except Exception:
                pass

        if dry_run:
            self._log("🟡 Dry run: post not written")
            return 0

        ASTRO_POSTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = ASTRO_POSTS_DIR / f"{slug}.md"
        out_path.write_text(final_markdown, encoding="utf-8")

        self._log(f"✅ Wrote: {out_path}")
        return 0
