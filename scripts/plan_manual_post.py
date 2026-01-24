from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from agents.affiliate_routing_agent import AffiliateRoutingAgent
from agents.product_agent import ProductDiscoveryAgent
from agents.title_optimization_agent import TitleOptimizationAgent
from agents.topic_agent import TopicSelectionAgent

from lib.product_catalog import ProductCatalog
from schemas.post_format import PostFormatId
from schemas.title import TitleOptimizationInput
from schemas.topic import TopicInput


DEFAULT_REGION = "UK"

CATALOG_PATH = Path("data/catalog/master.json")
POSTS_DIR = Path("data/posts")

NORMALIZE_TRANSLATION_TABLE = str.maketrans(
    {
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
    }
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_text(s: str) -> str:
    return (s or "").translate(NORMALIZE_TRANSLATION_TABLE)


def slugify(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9\-]", "", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


def _make_pick_anchor_id(title: str, idx: int) -> str:
    base = slugify(normalize_text(title))
    return f"pick-{idx+1}-{base}" if base else f"pick-{idx+1}"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Step 1 (manual pipeline): choose topic/title/products and create a plan + draft template."
    )
    p.add_argument("--date", required=True, help="Post date YYYY-MM-DD")
    p.add_argument("--topic", default="", help="Optional: force topic (skips TopicSelectionAgent)")
    p.add_argument("--category", default="", help="Optional: force category (used with --topic)")
    p.add_argument("--audience", default="", help="Optional: force audience (used with --topic)")
    p.add_argument("--format", default="top_picks", help="Format id (default: top_picks)")
    p.add_argument("--max-products", type=int, default=10, help="Max products (default: 10)")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    post_date = str(args.date).strip()
    format_id: PostFormatId = str(args.format).strip()  # type: ignore[assignment]

    forced_topic = normalize_text(args.topic).strip() or None
    forced_category = normalize_text(args.category).strip() or None
    forced_audience = normalize_text(args.audience).strip() or None

    # 1) Topic
    if forced_topic:
        topic_text = forced_topic
        topic_category = forced_category or "general"
        topic_audience = forced_audience or "UK readers"
    else:
        topic_agent = TopicSelectionAgent()
        t = topic_agent.run(TopicInput(current_date=post_date, region=DEFAULT_REGION))
        topic_text = normalize_text(t.topic)
        topic_category = normalize_text(t.category)
        topic_audience = normalize_text(t.audience)

    # 2) Affiliate routing (provider only)
    routing = AffiliateRoutingAgent().run(category=topic_category, topic=topic_text)
    provider_id = routing.provider_id

    # 3) Product suggestions (titles only)
    product_agent = ProductDiscoveryAgent()
    topic_ctx = SimpleNamespace(
        topic=topic_text,
        category=topic_category,
        audience=topic_audience,
        region=DEFAULT_REGION,
        provider_id=provider_id,
        format_id=format_id,
    )
    product_models = product_agent.run(topic_ctx)  # type: ignore[arg-type]

    raw_products: list[dict[str, Any]] = []
    for p in list(product_models)[: max(1, int(args.max_products))]:
        title = normalize_text(getattr(p, "title", "")).strip()
        if not title:
            continue
        raw_products.append(
            {
                "title": title,
                "description": normalize_text(getattr(p, "description", "")).strip(),
            }
        )

    # 4) Draft title (optimized)
    title_agent = TitleOptimizationAgent()
    title_inp = TitleOptimizationInput(
        topic=topic_text,
        primary_keyword=topic_text,
        secondary_keywords=[],
        existing_titles=[],
        num_candidates=int(os.getenv("MANUAL_TITLE_CANDIDATES", "25")),
        return_top_n=1,
        banned_starts=["Top", "Best"],
        voice="neutral",
    )
    title_out = title_agent.run(title_inp)
    selected_title = topic_text
    try:
        if isinstance(title_out, dict) and title_out.get("selected"):
            selected_title = normalize_text(title_out["selected"][0]["title"])
    except Exception:
        selected_title = topic_text

    post_slug = f"{post_date}-{slugify(selected_title)}"

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 5) Enrich with pick_id + catalog_key, seed master catalog with skeleton items (no overwrite)
    catalog = ProductCatalog(path=CATALOG_PATH)
    enriched: list[dict[str, Any]] = []
    for idx, p in enumerate(raw_products):
        title = p["title"]
        pick_id = _make_pick_anchor_id(title, idx)
        catalog_key = catalog.default_catalog_key(provider=provider_id, title=title)

        enriched.append(
            {
                "pick_id": pick_id,
                "catalog_key": catalog_key,
                "title": title,
                "description": p.get("description", ""),
                # hydrated later
                "affiliate_url": "",
                "rating": 0.0,
                "reviews_count": 0,
                "price": "",
                "asin": "",
            }
        )

    catalog.ensure_entries_for_products(provider=provider_id, products=enriched)

    # Plan JSON
    plan = {
        "version": 1,
        "post_slug": post_slug,
        "created_at": _utc_now_iso(),
        "date": post_date,
        "region": DEFAULT_REGION,
        "format_id": format_id,
        "topic": topic_text,
        "category": topic_category,
        "audience": topic_audience,
        "provider_id": provider_id,
        "draft_title": selected_title,
        "products": enriched,
        "notes": "Step 2 hydrates from data/catalog/master.json. Catalog is human-owned and never overwritten.",
    }

    plan_path = POSTS_DIR / f"{post_slug}.plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")

    # Draft template markdown with explicit tokens for Step 2 substitution
    md: list[str] = []
    md += [
        "---",
        f'title: "{selected_title}"',
        'description: "TBD"',
        f'publishedAt: "{_utc_now_iso()}"',
        f'category: "{topic_category}"',
        f'audience: "{topic_audience}"',
        'heroImage: ""',
        'heroAlt: ""',
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

    for p in enriched:
        title = p["title"]
        pick_id = p["pick_id"]
        key = p["catalog_key"]
        md += [
            f"<!-- pick_id: {pick_id} catalog_key: {key} -->",
            f"### {title}",
            "",
            f"- Rating: {{catalog:{key}:rating}}",
            f"- Reviews: {{catalog:{key}:reviews_count}}",
            f"- Price: {{catalog:{key}:price}}",
            f"- Link: {{catalog:{key}:affiliate_url}}",
            f"- ASIN: {{catalog:{key}:asin}}",
            "",
            f"{{{{PICK:{pick_id}}}}}",
            "",
            "<hr />",
            "",
        ]

    md += ["## Alternatives worth considering", "", "{{ALTERNATIVES}}", ""]

    draft_path = POSTS_DIR / f"{post_slug}.draft.md"
    draft_path.write_text("\n".join(md), encoding="utf-8")

    print(f"✅ Planned post: {post_slug}")
    print(f"🗂️  Plan:  {plan_path}")
    print(f"📝 Draft: {draft_path}")
    print(f"📚 Catalog: {CATALOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
