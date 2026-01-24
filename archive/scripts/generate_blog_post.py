from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from agents.affiliate_routing_agent import AffiliateRoutingAgent
from agents.depth_expansion_agent import DepthExpansionAgent
from agents.final_title_agent import FinalTitleAgent, FinalTitleConfig
from agents.image_generation_agent import ImageGenerationAgent
from agents.post_repair_agent import PostRepairAgent, PostRepairConfig
from agents.preflight_qa_agent import PreflightQAAgent
from agents.product_agent import ProductDiscoveryAgent
from agents.title_optimization_agent import TitleOptimizationAgent
from agents.topic_agent import TopicSelectionAgent

from integrations.openai_adapters import OpenAIImageGenerator, OpenAIJsonLLM
from pipeline.image_step import generate_hero_image

from schemas.depth import DepthExpansionInput, ExpansionModuleSpec
from schemas.post_format import PostFormatId
from schemas.title import TitleOptimizationInput
from schemas.topic import TopicInput

from lib.affiliates_config_loader import load_affiliates_config
from lib.post_formats import get_format_spec
from lib.topic_overrides import load_topic_override_for_date

# ✅ Catalog + manifest
from lib.post_manifest import write_post_manifest
from lib.product_catalog import ProductCatalog


ASTRO_POSTS_DIR = Path("site/src/content/posts")
LOG_PATH = Path("output/posts_log.json")
FAILED_POSTS_DIR = Path("output/failed_posts")

PUBLIC_IMAGES_DIR = Path("site/public/images")
PUBLIC_POST_IMAGES_DIR = PUBLIC_IMAGES_DIR / "posts"
PLACEHOLDER_HERO_PATH = PUBLIC_IMAGES_DIR / "placeholder-hero.webp"

DEFAULT_IMAGE_CREDIT_NAME = None
DEFAULT_IMAGE_CREDIT_URL = None

OPTION_B_MODE = True
MAX_REPAIR_ATTEMPTS = 1

DEFAULT_REGION = "UK"

# ✅ Central catalog path
CATALOG_PATH = Path("output/catalog/manual_product_catalog.json")


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9\-]", "", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


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


def ensure_log_file():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LOG_PATH.exists():
        LOG_PATH.write_text("[]", encoding="utf-8")


def append_log(entry: dict):
    ensure_log_file()
    try:
        data = json.loads(LOG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            data = []
    except Exception:
        data = []
    data.append(entry)
    LOG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def estimate_word_count(text: str) -> int:
    return len((text or "").strip().split())


def product_passes_filter(p) -> bool:
    if OPTION_B_MODE:
        return True
    return (
        p.rating is not None
        and p.reviews_count is not None
        and float(p.rating) >= 4.0
        and int(p.reviews_count) >= 250
    )


def safe_float(x):
    try:
        return float(x) if x is not None else None
    except Exception:
        return None


def safe_int(x):
    try:
        return int(x) if x is not None else None
    except Exception:
        return None


def _dedupe_products(products: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for p in products:
        key = normalize_text(p.get("title", "")).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _make_pick_anchor_id(title: str, idx: int) -> str:
    base = slugify(normalize_text(title))
    if not base:
        base = f"pick-{idx+1}"
    return f"pick-{idx+1}-{base}"


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
                if cur.startswith("### ") or cur.startswith("## "):
                    break
                if cur.lower() == "<hr />":
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

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return markdown

    fm = lines[:end_idx]
    body = lines[end_idx:]

    prefix = f"{key}:"
    fm = [l for l in fm if not l.startswith(prefix)]

    insert_at = len(fm)
    for i, l in enumerate(fm):
        if l.startswith("title:"):
            insert_at = i + 1
            break

    fm.insert(insert_at, f'{key}: "{value}"')
    return "\n".join(fm + body)


def _parse_frontmatter(markdown: str) -> dict:
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}

    fm_lines = lines[1:end_idx]
    out: dict = {}
    for l in fm_lines:
        if ":" not in l:
            continue
        k, v = l.split(":", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


def _run_preflight(
    *,
    qa_agent: PreflightQAAgent,
    markdown: str,
    intro_text: str,
    picks_texts: list[str],
    products: list[dict],
) -> dict:
    fm = _parse_frontmatter(markdown)
    report = qa_agent.run(
        final_markdown=markdown,
        frontmatter=fm,
        intro_text=intro_text,
        picks_texts=picks_texts,
        products=products,
    )
    return report.model_dump()


def _compile_signal_regex(signals: list[str]) -> re.Pattern[str]:
    parts = [
        re.escape(s.strip())
        for s in sorted({s for s in signals if (s or "").strip()}, key=len, reverse=True)
    ]
    if not parts:
        return re.compile(r"a^")
    return re.compile(r"|".join(parts), re.IGNORECASE)


def _infer_category_for_forced_topic(forced_topic: str) -> str:
    cfg = load_affiliates_config()
    signals = cfg.signal_groups.get("outdoor_gear", [])
    rx = _compile_signal_regex(signals)
    return "travel" if rx.search(forced_topic or "") else "home"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AI Affiliate Engine post generator (UK default).")
    p.add_argument(
        "--format",
        choices=["top_picks", "deep_dive", "use_case_kit"],
        default="top_picks",
        help="Post format style (no scheduling yet).",
    )
    p.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="ISO date YYYY-MM-DD used for filename and topic overrides (default: today).",
    )
    p.add_argument(
        "--topic",
        default=None,
        help="Optional: force a specific topic string (bypasses topic generation).",
    )
    p.add_argument(
        "--category",
        choices=["home", "travel", "gadgets", "pets", "kids", "health"],
        default=None,
        help="Optional: force category when using --topic. If omitted, we infer home vs travel using config signals.",
    )
    p.add_argument(
        "--audience",
        default=None,
        help="Optional: force audience when using --topic (otherwise defaults).",
    )
    p.add_argument(
        "--topic-overrides",
        default="config/topic_overrides.yaml",
        help="YAML file containing date->topic overrides.",
    )
    return p.parse_args()


def main():
    args = _parse_args()
    format_id: PostFormatId = args.format  # type: ignore[assignment]
    format_spec = get_format_spec(format_id)

    print(">>> generate_blog_post.py started")
    print(f"🧭 Region default: {DEFAULT_REGION}")
    print(f"🧩 Format: {format_id}")

    ASTRO_POSTS_DIR.mkdir(parents=True, exist_ok=True)
    FAILED_POSTS_DIR.mkdir(parents=True, exist_ok=True)

    post_date = args.date
    published_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )

    # 1) Topic (override > CLI topic > agent)
    forced_topic = (args.topic or "").strip() or None
    override = load_topic_override_for_date(
        date_str=post_date,
        overrides_path=Path(args.topic_overrides),
    )

    if override:
        topic_text = override.topic
        topic_category = override.category
        topic_audience = override.audience
        print("📝 Topic override applied:", topic_text)

    elif forced_topic:
        topic_text = forced_topic
        topic_category = args.category or _infer_category_for_forced_topic(forced_topic)
        topic_audience = args.audience or "UK readers"
        print("📝 CLI topic forced:", topic_text)
        print("🏷️ Category:", topic_category)

    else:
        topic_agent = TopicSelectionAgent()
        input_data = TopicInput(current_date=post_date, region=DEFAULT_REGION)
        try:
            topic = topic_agent.run(input_data)
            topic_text = topic.topic
            topic_category = topic.category
            topic_audience = topic.audience
            print("✅ Topic generated:", topic_text)
        except Exception as e:
            print("Error generating topic:", e)
            return

    # 2) Affiliate routing (config-driven)
    routing = AffiliateRoutingAgent().run(category=topic_category, topic=topic_text)
    provider_id = routing.provider_id
    print(f"🔗 Affiliate provider selected: {provider_id} ({routing.reason})")

    # 3) Products
    product_agent = ProductDiscoveryAgent()
    try:
        topic_ctx = SimpleNamespace(
            topic=topic_text,
            category=topic_category,
            audience=topic_audience,
            region=DEFAULT_REGION,
            provider_id=provider_id,
            format_id=format_id,
        )
        product_models = product_agent.run(topic_ctx)  # type: ignore[arg-type]
        print(f"✅ {len(product_models)} products generated")
    except Exception as e:
        print("Error generating products:", e)
        return

    # 4) Filter + normalize
    products: list[dict] = []
    for p in product_models:
        if not product_passes_filter(p):
            continue
        products.append(
            {
                "title": normalize_text(p.title),
                "amazon_search_query": getattr(p, "amazon_search_query", None),
                "url": str(p.url) if getattr(p, "url", None) is not None else None,
                "price": str(p.price) if getattr(p, "price", None) is not None else None,
                "rating": safe_float(getattr(p, "rating", None)),
                "reviews_count": safe_int(getattr(p, "reviews_count", None)),
                "description": normalize_text(p.description),
            }
        )

    products = _dedupe_products(products)
    products = sorted(
        products,
        key=lambda p: (
            p.get("rating") is not None,
            p.get("rating") or 0,
            p.get("reviews_count") or 0,
        ),
        reverse=True,
    )

    # Apply format pick count target
    target_count = format_spec.pick_count_target()
    if len(products) > target_count:
        products = products[:target_count]

    if len(products) < 5 and format_id == "top_picks":
        print("⚠️ Warning: fewer than 5 products available for top_picks format.")

    # 5) Title optimization (draft)
    existing_titles: list[str] = []
    try:
        if LOG_PATH.exists():
            prior = json.loads(LOG_PATH.read_text(encoding="utf-8"))
            if isinstance(prior, list):
                existing_titles = [
                    normalize_text(x.get("title", ""))
                    for x in prior
                    if isinstance(x, dict) and x.get("title")
                ]
    except Exception:
        existing_titles = []

    title_agent = TitleOptimizationAgent()
    title_inp = TitleOptimizationInput(
        topic=normalize_text(topic_text),
        primary_keyword=normalize_text(topic_text),
        secondary_keywords=[],
        existing_titles=existing_titles,
        num_candidates=40,
        return_top_n=3,
        banned_starts=["Top", "Top Cozy", "Top cosy", "Best", "Best Cozy", "Best cosy"],
        voice="neutral",
    )

    title_out = title_agent.run(title_inp)
    selected_title = normalize_text(topic_text)
    try:
        if isinstance(title_out, dict) and title_out.get("selected"):
            selected_title = normalize_text(title_out["selected"][0]["title"])
    except Exception:
        selected_title = normalize_text(topic_text)

    print("✅ Selected title:", selected_title)

    # 6) File naming
    slug = slugify(selected_title)
    filename = f"{post_date}-{slug}.md"
    file_path = ASTRO_POSTS_DIR / filename
    post_slug = f"{post_date}-{slug}"

    # ✅ Attach pick_id + catalog_key deterministically
    catalog = ProductCatalog(path=CATALOG_PATH)
    enriched_products: list[dict] = []
    for idx, p in enumerate(products):
        title = normalize_text(p.get("title", "")).strip() or f"Product {idx+1}"
        pick_id = _make_pick_anchor_id(title, idx)
        catalog_key = catalog.default_catalog_key(provider=provider_id, title=title)
        p2 = dict(p)
        p2["pick_id"] = pick_id
        p2["catalog_key"] = catalog_key
        enriched_products.append(p2)

    products = enriched_products

    # ✅ Seed central catalog with skeleton entries for any new products
    try:
        created = catalog.ensure_entries_for_products(provider=provider_id, products=products)
        if created:
            catalog.save()
            print(f"📚 Catalog updated: added {created} new product(s) to {CATALOG_PATH}")
        else:
            print(f"📚 Catalog unchanged: all products already present in {CATALOG_PATH}")
    except Exception as e:
        print("⚠️ Unable to update central product catalog:", e)

    # 7) Frontmatter
    meta_description = (
        f"Curated {topic_category.replace('_', ' ')} picks for {normalize_text(topic_audience)}."
    )

    astro_products: list[dict] = []
    for p in products:
        astro_products.append(
            {
                "pick_id": p.get("pick_id") or "",
                "catalog_key": p.get("catalog_key") or "",
                "title": p.get("title") or "",
                # ✅ IMPORTANT: until hydrated, leave blank so UI can show "Link needed"
                "url": p.get("url") or "",
                "price": p.get("price") or "—",
                "rating": float(p.get("rating")) if p.get("rating") is not None else 0.0,
                "reviews_count": int(p.get("reviews_count"))
                if p.get("reviews_count") is not None
                else 0,
                "description": p.get("description") or "",
                "amazon_search_query": p.get("amazon_search_query"),
            }
        )

    md: list[str] = []
    md.append("---")
    md.append(f'title: "{normalize_text(selected_title)}"')
    md.append(f'description: "{meta_description}"')
    md.append(f'publishedAt: "{published_at}"')
    md.append(f'category: "{topic_category}"')
    md.append(f'audience: "{normalize_text(topic_audience)}"')
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

    for idx, p in enumerate(products):
        t = normalize_text(p.get("title", "")).strip() or f"Product {idx+1}"
        pick_id = str(p.get("pick_id") or _make_pick_anchor_id(t, idx))

        # ✅ Stable marker for hydrator / debugging
        md.append(f"<!-- pick_id: {pick_id} -->")
        md.append(f"### {t}")
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
    before_wc = estimate_word_count(draft_markdown)

    # 8) Depth expansion
    depth_agent = DepthExpansionAgent()
    modules = [
        ExpansionModuleSpec(
            name="intro", enabled=True, max_words=format_spec.max_words_intro, rewrite_mode="upgrade"
        ),
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
    after_wc = estimate_word_count(final_markdown)

    intro_text = _extract_section(final_markdown, "Intro")
    picks_texts = _extract_picks(final_markdown)
    alternatives_text = _extract_section(final_markdown, "Alternatives worth considering")

    # 9) Final title pass
    max_chars = int(os.getenv("TITLE_MAX_CHARS", "60"))
    try:
        llm = OpenAIJsonLLM()
        final_title_agent = FinalTitleAgent(
            llm=llm,
            config=FinalTitleConfig(max_chars=max_chars),
        )
        final_title = final_title_agent.run(
            topic=normalize_text(topic_text),
            category=topic_category,
            intro=intro_text or normalize_text(topic_text),
            picks=picks_texts,
            products=products,
            alternatives=alternatives_text or None,
        )
        final_markdown = _replace_frontmatter_field(final_markdown, "title", final_title)
        print("✅ Final Title (post-body):", final_title)
    except Exception as e:
        print("⚠️ Final title pass unavailable, keeping initial title:", e)

    # 10) Hero image generation
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
            title=normalize_text(topic_text),
            intro=intro_text or normalize_text(topic_text),
            picks=picks_texts,
            alternatives=alternatives_text or None,
        )
        hero_image_url, hero_alt = hero.hero_image_path, hero.hero_alt
        print("✅ Hero image ready:", hero_image_url)

    except Exception as e:
        print("⚠️ Hero image generation unavailable, using placeholder:", e)
        hero_image_url, hero_alt = _copy_placeholder_hero(post_slug)

    final_markdown = _replace_frontmatter_field(final_markdown, "heroImage", hero_image_url)
    final_markdown = _replace_frontmatter_field(final_markdown, "heroAlt", hero_alt)

    if DEFAULT_IMAGE_CREDIT_NAME:
        final_markdown = _replace_frontmatter_field(
            final_markdown, "imageCreditName", DEFAULT_IMAGE_CREDIT_NAME
        )
    if DEFAULT_IMAGE_CREDIT_URL:
        final_markdown = _replace_frontmatter_field(
            final_markdown, "imageCreditUrl", DEFAULT_IMAGE_CREDIT_URL
        )

    # ✅ Write per-post manifest (receipt / to-do list)
    try:
        manifest_path = write_post_manifest(
            post_slug=post_slug,
            provider=provider_id,
            products=products,
        )
        print(f"🧾 Post manifest written: {manifest_path}")
    except Exception as e:
        print("⚠️ Unable to write post manifest:", e)

    # 11) Preflight QA + single repair attempt
    strict = os.getenv("PREFLIGHT_STRICT", "1").strip() not in {"0", "false", "False"}
    qa_agent = PreflightQAAgent(strict=strict)

    qa_initial = _run_preflight(
        qa_agent=qa_agent,
        markdown=final_markdown,
        intro_text=intro_text,
        picks_texts=picks_texts,
        products=products,
    )

    repair_attempted = False
    qa_after_repair = None
    repair_changes: list[str] = []

    if not qa_initial.get("ok", False) and MAX_REPAIR_ATTEMPTS > 0:
        repair_attempted = True
        print("🛠️ Preflight QA failed. Attempting one targeted auto-repair...")

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
        repair_changes = (
            repair_out.get("changes_made", []) if isinstance(repair_out.get("changes_made"), list) else []
        )

        intro_text = _extract_section(final_markdown, "Intro")
        picks_texts = _extract_picks(final_markdown)
        alternatives_text = _extract_section(final_markdown, "Alternatives worth considering")

        qa_after_repair = _run_preflight(
            qa_agent=qa_agent,
            markdown=final_markdown,
            intro_text=intro_text,
            picks_texts=picks_texts,
            products=products,
        )

    final_ok = qa_after_repair["ok"] if qa_after_repair is not None else qa_initial["ok"]

    if not final_ok:
        failed_path = FAILED_POSTS_DIR / filename
        failed_path.write_text(final_markdown, encoding="utf-8")

        print("❌ Preflight QA failed after repair. Post NOT published.")
        append_log(
            {
                "date": post_date,
                "publishedAt": published_at,
                "title_initial": normalize_text(selected_title),
                "topic": normalize_text(topic_text),
                "category": topic_category,
                "audience": normalize_text(topic_audience),
                "file_failed": str(failed_path).replace("\\", "/"),
                "product_count": len(products),
                "heroImage": hero_image_url,
                "word_count_before": before_wc,
                "word_count_after": after_wc,
                "format_id": format_id,
                "affiliate_provider": provider_id,
                "depth_modules_applied": depth_out.get("applied_modules", []),
                "qa_initial": qa_initial,
                "repair_attempted": repair_attempted,
                "repair_changes": repair_changes,
                "qa_after_repair": qa_after_repair,
            }
        )
        print(f"✅ Failed draft saved to {failed_path}")
        print(f"✅ Failure logged in {LOG_PATH}")
        return

    warnings = (qa_after_repair or qa_initial).get("warnings", [])
    if warnings:
        print("⚠️ Preflight QA warnings:")
        for w in warnings:
            print("   -", w)

    file_path.write_text(final_markdown, encoding="utf-8")
    print(f"✅ Astro post saved to {file_path}")

    append_log(
        {
            "date": post_date,
            "publishedAt": published_at,
            "title_initial": normalize_text(selected_title),
            "topic": normalize_text(topic_text),
            "category": topic_category,
            "audience": normalize_text(topic_audience),
            "file": str(file_path).replace("\\", "/"),
            "product_count": len(products),
            "heroImage": hero_image_url,
            "word_count_before": before_wc,
            "word_count_after": after_wc,
            "format_id": format_id,
            "affiliate_provider": provider_id,
            "depth_modules_applied": depth_out.get("applied_modules", []),
            "title_candidates_top3": (title_out.get("selected", [])[:3] if isinstance(title_out, dict) else []),
            "qa_initial": qa_initial,
            "repair_attempted": repair_attempted,
            "repair_changes": repair_changes,
            "qa_after_repair": qa_after_repair,
        }
    )
    print(f"✅ Post logged in {LOG_PATH}")


if __name__ == "__main__":
    main()
