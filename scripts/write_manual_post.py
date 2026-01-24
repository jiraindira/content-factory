from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.depth_expansion_agent import DepthExpansionAgent
from agents.final_title_agent import FinalTitleAgent, FinalTitleConfig
from agents.image_generation_agent import ImageGenerationAgent
from agents.post_repair_agent import PostRepairAgent, PostRepairConfig
from agents.preflight_qa_agent import PreflightQAAgent

from integrations.openai_adapters import OpenAIImageGenerator, OpenAIJsonLLM
from pipeline.image_step import generate_hero_image

from schemas.depth import DepthExpansionInput, ExpansionModuleSpec
from schemas.post_format import PostFormatId
from lib.post_formats import get_format_spec
from lib.env import load_env

load_env()

ASTRO_POSTS_DIR = Path("site/src/content/posts")
POSTS_DIR = Path("data/posts")

PUBLIC_IMAGES_DIR = Path("site/public/images")
PUBLIC_POST_IMAGES_DIR = PUBLIC_IMAGES_DIR / "posts"
PLACEHOLDER_HERO_PATH = PUBLIC_IMAGES_DIR / "placeholder-hero.webp"

MAX_REPAIR_ATTEMPTS = 1

NORMALIZE_TRANSLATION_TABLE = str.maketrans(
    {
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
    }
)


def normalize_text(s: str) -> str:
    return (s or "").translate(NORMALIZE_TRANSLATION_TABLE)


def slugify(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9\-]", "", text)
    text = re.sub(r"-{2,}", "-", s=text)
    return text.strip("-")


def estimate_word_count(text: str) -> int:
    return len((text or "").strip().split())


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _set_plan_status(plan_path: Path, status: str, extra: dict[str, Any] | None = None) -> None:
    try:
        plan = _read_json(plan_path)
        plan["status"] = status
        plan["status_updated_at"] = _utc_now_iso()
        if extra:
            plan.setdefault("status_meta", {})
            if isinstance(plan["status_meta"], dict):
                plan["status_meta"].update(extra)
        _write_json(plan_path, plan)
    except Exception:
        # Never fail the post run due to status writes
        pass


def _copy_placeholder_hero(post_slug: str) -> tuple[str, str]:
    PUBLIC_POST_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    post_img_dir = PUBLIC_POST_IMAGES_DIR / post_slug
    post_img_dir.mkdir(parents=True, exist_ok=True)

    hero_file = post_img_dir / "hero.webp"
    hero_url = f"/images/posts/{post_slug}/hero.webp"

    if hero_file.exists():
        return hero_url, "Hero image for the guide"

    if not PLACEHOLDER_HERO_PATH.exists():
        raise FileNotFoundError(
            f"Missing placeholder hero image at {PLACEHOLDER_HERO_PATH}. "
            "Add site/public/images/placeholder-hero.webp so the generator can auto-fill missing heroes."
        )

    shutil.copyfile(PLACEHOLDER_HERO_PATH, hero_file)
    return hero_url, "Placeholder hero image"


def _extract_section(markdown: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    lines = markdown.splitlines()

    start = None
    for i, line in enumerate(lines):
        if re.match(pattern, line.strip()):
            start = i + 1
            break
    if start is None:
        return ""

    out: list[str] = []
    for j in range(start, len(lines)):
        if lines[j].startswith("## "):
            break
        out.append(lines[j])
    return "\n".join(out).strip()


def _extract_picks(markdown: str) -> list[str]:
    picks_block = _extract_section(markdown, "The picks")
    if not picks_block:
        return []
    lines = picks_block.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("### "):
            i += 1
            buf: list[str] = []
            while i < len(lines):
                cur = lines[i].strip()
                if cur.startswith("### ") or cur.startswith("## ") or cur.lower() == "<hr />":
                    break
                buf.append(lines[i])
                i += 1
            text = "\n".join(buf).strip()
            if text:
                out.append(text)
        else:
            i += 1
    return out


def _replace_frontmatter_field(markdown: str, key: str, value: str) -> str:
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return markdown

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return markdown

    found = False
    for i in range(1, end):
        if lines[i].startswith(f"{key}:"):
            lines[i] = f'{key}: "{value}"'
            found = True
            break

    if not found:
        lines.insert(end, f'{key}: "{value}"')

    return "\n".join(lines)


def _parse_frontmatter(md_text: str) -> dict[str, Any]:
    """
    Minimal YAML-ish frontmatter parser sufficient for QA.
    - Handles key: "value" and key: value
    - Ignores complex structures
    """
    lines = md_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}

    fm: dict[str, Any] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
            v = v[1:-1]
        fm[k] = v
    return fm


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Step 3 (manual pipeline): write + QA from a hydrated plan.")
    p.add_argument("--post-slug", required=True, help="Post slug, e.g. 2026-01-23-some-slug")
    p.add_argument("--dry-run", action="store_true", help="Run agents and QA but do not write output file")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    post_slug = str(args.post_slug).strip()

    plan_path = POSTS_DIR / f"{post_slug}.plan.json"
    if not plan_path.exists():
        raise FileNotFoundError(f"Missing plan: {plan_path}. Run plan_manual_post.py first.")

    print(f"🟡 Step 3: start write_manual_post for slug={post_slug}")
    print(f"📄 Plan: {plan_path}")

    plan = _read_json(plan_path)
    _set_plan_status(plan_path, "writing", {"slug": post_slug})

    format_id: PostFormatId = str(plan.get("format_id") or "top_picks")  # type: ignore[assignment]
    format_spec = get_format_spec(format_id)

    topic_text = normalize_text(plan.get("topic", ""))
    topic_category = normalize_text(plan.get("category", "general"))
    topic_audience = normalize_text(plan.get("audience", "UK readers"))
    selected_title = normalize_text(plan.get("draft_title", topic_text))

    products = plan.get("products", [])
    if not isinstance(products, list) or not products:
        raise ValueError("Plan has no products. Did Step 1 succeed?")

    print(f"🧺 Products in plan: {len(products)}")

    # Build Astro frontmatter products array
    astro_products: list[dict[str, Any]] = []
    for p in products:
        if not isinstance(p, dict):
            continue
        astro_products.append(
            {
                "pick_id": p.get("pick_id") or "",
                "catalog_key": p.get("catalog_key") or "",
                "title": p.get("title") or "",
                "url": p.get("affiliate_url") or "",
                "price": p.get("price") or "—",
                "rating": float(p.get("rating") or 0.0),
                "reviews_count": int(p.get("reviews_count") or 0),
                "description": p.get("description") or "",
                "amazon_search_query": p.get("amazon_search_query"),
            }
        )

    published_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    meta_description = f"Curated {topic_category.replace('_', ' ')} picks for {topic_audience}."

    # Draft scaffold
    md: list[str] = []
    md.append("---")
    md.append(f'title: "{selected_title}"')
    md.append(f'description: "{meta_description}"')
    md.append(f'publishedAt: "{published_at}"')
    md.append(f'category: "{topic_category}"')
    md.append(f'audience: "{topic_audience}"')
    md.append(f"products: {json.dumps(astro_products, ensure_ascii=False)}")
    md.append("---")
    md.append("")
    md.append("## Intro")
    md.append("")
    md.append("{{INTRO}}")
    md.append("")
    md.append("## How this list was chosen")
    md.append("")
    md.append("{{HOW_WE_CHOSE}}")
    md.append("")
    md.append("## The picks")
    md.append("")

    for p in products:
        title = normalize_text(p.get("title", "")).strip() or "Product"
        pick_id = str(p.get("pick_id") or "")
        md.append(f"<!-- pick_id: {pick_id} -->")
        md.append(f"### {title}")
        md.append("")
        md.append(f"{{{{PICK:{pick_id}}}}}")
        md.append("")
        md.append("<hr />")
        md.append("")

    md.append("## Alternatives worth considering")
    md.append("")
    md.append("{{ALTERNATIVES}}")
    md.append("")

    draft_markdown = "\n".join(md)
    print("✍️  Draft scaffold built")

    # Depth expansion (writing)
    print("🧠 Running DepthExpansionAgent…")
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
            name="alternatives",
            enabled=True,
            max_words=format_spec.max_words_alternatives,
            rewrite_mode="upgrade",
        ),
        ExpansionModuleSpec(
            name="product_writeups",
            enabled=True,
            max_words=format_spec.max_words_product_writeups,
            rewrite_mode="upgrade",
        ),
    ]

    depth_inp = DepthExpansionInput(
        draft_markdown=draft_markdown,
        products=products,
        modules=modules,
        rewrite_mode="upgrade",
        max_added_words=(
            format_spec.max_words_intro
            + format_spec.max_words_how_we_chose
            + format_spec.max_words_alternatives
            + format_spec.max_words_product_writeups
        ),
        voice="neutral",
        faqs=[],
        forbid_claims_of_testing=True,
    )

    depth_out = depth_agent.run(depth_inp)
    final_markdown = depth_out.get("expanded_markdown", draft_markdown)
    print("✅ Content generated by DepthExpansionAgent")

    intro_text = _extract_section(final_markdown, "Intro")
    picks_texts = _extract_picks(final_markdown)
    alternatives_text = _extract_section(final_markdown, "Alternatives worth considering")

    # Final title pass
    print("🏷️  Final title pass…")
    try:
        max_chars = int(os.getenv("TITLE_MAX_CHARS", "60"))
        llm = OpenAIJsonLLM()
        final_title_agent = FinalTitleAgent(llm=llm, config=FinalTitleConfig(max_chars=max_chars))
        final_title = final_title_agent.run(
            topic=topic_text,
            category=topic_category,
            intro=intro_text or topic_text,
            picks=picks_texts,
            products=products,
            alternatives=alternatives_text or None,
        )
        final_markdown = _replace_frontmatter_field(final_markdown, "title", final_title)
        print(f"✅ Title selected: {final_title}")
    except Exception as e:
        print(f"⚠️ Title pass skipped due to error: {e}")

    # Hero image
    print("🖼️  Hero image…")
    try:
        llm = OpenAIJsonLLM()
        img = OpenAIImageGenerator()
        image_agent = ImageGenerationAgent(
            llm=llm,
            image_gen=img,
            public_images_dir=str(PUBLIC_IMAGES_DIR),
            posts_subdir="posts",
            width=1400,
            height=800,
        )
        hero = generate_hero_image(
            agent=image_agent,
            slug=post_slug,
            category=topic_category,
            title=topic_text,
            intro=intro_text or topic_text,
            picks=picks_texts,
            alternatives=alternatives_text or None,
        )
        hero_image_url, hero_alt = hero.hero_image_path, hero.hero_alt
        print(f"✅ Hero image generated: {hero_image_url}")
    except Exception as e:
        print(f"⚠️ Hero image generation failed, using placeholder. Reason: {e}")
        hero_image_url, hero_alt = _copy_placeholder_hero(post_slug)
        print(f"✅ Placeholder hero image: {hero_image_url}")

    final_markdown = _replace_frontmatter_field(final_markdown, "heroImage", hero_image_url)
    final_markdown = _replace_frontmatter_field(final_markdown, "heroAlt", hero_alt)

    # Preflight QA + repair
    strict = os.getenv("PREFLIGHT_STRICT", "1").strip() not in {"0", "false", "False"}
    qa_agent = PreflightQAAgent(strict=strict)

    def run_qa(md_text: str) -> dict[str, Any]:
        frontmatter = _parse_frontmatter(md_text)
        return qa_agent.run(
            final_markdown=md_text,
            frontmatter=frontmatter,
            intro_text=_extract_section(md_text, "Intro"),
            picks_texts=_extract_picks(md_text),
            products=products,
        )

    print("🔎 Running Preflight QA…")
    qa_initial = run_qa(final_markdown)
    try:
        ok = bool(getattr(qa_initial, "ok", False)) if not isinstance(qa_initial, dict) else bool(qa_initial.get("ok"))
    except Exception:
        ok = False

    if not ok and MAX_REPAIR_ATTEMPTS > 0:
        print("🧯 QA failed, attempting repair…")
        try:
            llm = OpenAIJsonLLM()
            repair_agent = PostRepairAgent(llm=llm, config=PostRepairConfig(max_changes=12))
            repair_out = repair_agent.run(
                draft_markdown=final_markdown,
                qa_report=qa_initial,
                products=products,
                intro_text=intro_text,
                picks_texts=picks_texts,
            )
            final_markdown = repair_out.get("repaired_markdown", final_markdown)
            qa_after = run_qa(final_markdown)
            try:
                ok = (
                    bool(getattr(qa_after, "ok", False))
                    if not isinstance(qa_after, dict)
                    else bool(qa_after.get("ok"))
                )
            except Exception:
                ok = False
            print("✅ Repair attempted")
        except Exception as e:
            print(f"⚠️ Repair skipped due to error: {e}")

    if ok:
        print("✅ QA passed")
        _set_plan_status(plan_path, "qa_passed")
    else:
        print("⚠️ QA did not pass (continuing to write output so you can inspect).")
        _set_plan_status(plan_path, "qa_failed")

    # Write final Astro post
    ASTRO_POSTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{post_slug}.md"
    out_path = ASTRO_POSTS_DIR / filename

    if args.dry_run:
        print("🧪 Dry run enabled: not writing output file")
        print(f"📄 Would write: {out_path.resolve()}")
        _set_plan_status(plan_path, "written", {"dry_run": True, "output_path": str(out_path)})
        return 0

    out_path.write_text(final_markdown, encoding="utf-8")
    _set_plan_status(plan_path, "written", {"output_path": str(out_path)})

    print(f"🎉 Wrote: {out_path.resolve()} ({estimate_word_count(final_markdown)} words)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
