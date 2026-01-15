from agents.topic_agent import TopicSelectionAgent
from agents.product_agent import ProductDiscoveryAgent
from agents.title_optimization_agent import TitleOptimizationAgent
from agents.depth_expansion_agent import DepthExpansionAgent
from agents.image_generation_agent import ImageGenerationAgent
from agents.final_title_agent import FinalTitleAgent, FinalTitleConfig

from integrations.openai_adapters import OpenAIImageGenerator, OpenAIJsonLLM
from pipeline.image_step import generate_hero_image

from schemas.topic import TopicInput
from schemas.title import TitleOptimizationInput
from schemas.depth import DepthExpansionInput, ExpansionModuleSpec

from datetime import date, datetime, timezone
from pathlib import Path
import json
import os
import re
import shutil


ASTRO_POSTS_DIR = Path("site/src/content/posts")
LOG_PATH = Path("output/posts_log.json")

# Image convention (public/)
PUBLIC_IMAGES_DIR = Path("site/public/images")
PUBLIC_POST_IMAGES_DIR = PUBLIC_IMAGES_DIR / "posts"
PLACEHOLDER_HERO_PATH = PUBLIC_IMAGES_DIR / "placeholder-hero.webp"

# Optional image credit fields (Astro schema makes them optional; omit if None)
DEFAULT_IMAGE_CREDIT_NAME = None  # e.g. "Unsplash"
DEFAULT_IMAGE_CREDIT_URL = None   # e.g. "https://unsplash.com/photos/abc123"

# Option B mode: no Amazon API yet, so rating/review/price/url may be None
OPTION_B_MODE = True


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9\-]", "", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


NORMALIZE_TRANSLATION_TABLE = str.maketrans({
    "’": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
})


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
    """
    In Option B mode we don't have real rating/reviews yet, so we keep everything.
    Once you have an API, set OPTION_B_MODE=False to enforce quality thresholds.
    """
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
    """
    Deduplicate products by normalized title while preserving order.
    """
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
    """
    Stable ID used for placeholder keys (agent replacement) and optional linking.
    Keep deterministic and filesystem-safe.
    """
    base = slugify(normalize_text(title))
    if not base:
        base = f"pick-{idx+1}"
    return f"pick-{idx+1}-{base}"


def _copy_placeholder_hero(post_slug: str) -> tuple[str, str]:
    """
    Fallback: copy placeholder hero into the post folder.
    Disk: site/public/images/posts/<post_slug>/hero.webp
    URL:  /images/posts/<post_slug>/hero.webp
    """
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
    """
    Extracts the content under a '## {heading}' until the next '## ' heading.
    """
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
    """
    Extract pick paragraphs for each ### heading under '## The picks'.

    Strategy:
      - Find the '## The picks' section block
      - Within it, for each '### ' heading, grab following paragraph text until <hr /> or next ###/##
    """
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
    """
    Replace or insert a frontmatter field key: "value" within the top YAML block.
    Assumes markdown starts with --- frontmatter ---.
    """
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

    # Remove existing occurrences
    prefix = f"{key}:"
    fm = [l for l in fm if not l.startswith(prefix)]

    # Insert near top after the initial ---
    # Keep ordering tidy: insert after title if we can, otherwise append
    insert_at = len(fm)
    for i, l in enumerate(fm):
        if l.startswith("title:"):
            insert_at = i + 1
            break

    fm.insert(insert_at, f'{key}: "{value}"')
    return "\n".join(fm + body)


def main():
    print(">>> generate_blog_post.py started")

    ASTRO_POSTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Topic
    topic_agent = TopicSelectionAgent()
    input_data = TopicInput(current_date=date.today().isoformat(), region="US")

    try:
        topic = topic_agent.run(input_data)
        print("✅ Topic generated:", topic.topic)
    except Exception as e:
        print("Error generating topic:", e)
        return

    # 2) Products
    product_agent = ProductDiscoveryAgent()
    try:
        product_models = product_agent.run(topic)
        print(f"✅ {len(product_models)} products generated")
    except Exception as e:
        print("Error generating products:", e)
        return

    # 3) Filter + normalize + convert to JSON-safe dicts
    products: list[dict] = []
    for p in product_models:
        if not product_passes_filter(p):
            continue

        products.append({
            "title": normalize_text(p.title),
            "amazon_search_query": getattr(p, "amazon_search_query", None),
            "url": str(p.url) if getattr(p, "url", None) is not None else None,
            "price": str(p.price) if getattr(p, "price", None) is not None else None,
            "rating": safe_float(getattr(p, "rating", None)),
            "reviews_count": safe_int(getattr(p, "reviews_count", None)),
            "description": normalize_text(p.description),
        })

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

    if len(products) < 5:
        print("⚠️ Warning: fewer than 5 products passed filters.")

    # 4) Initial title (used for slug/filename; we DO NOT rename later)
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
        topic=normalize_text(topic.topic),
        primary_keyword=normalize_text(topic.topic),
        secondary_keywords=[],
        existing_titles=existing_titles,
        num_candidates=40,
        return_top_n=3,
        banned_starts=["Top", "Top Cozy", "Top cosy", "Best", "Best Cozy", "Best cosy"],
        voice="neutral",
    )

    title_out = title_agent.run(title_inp)
    selected_title = normalize_text(topic.topic)
    try:
        if isinstance(title_out, dict) and title_out.get("selected"):
            selected_title = normalize_text(title_out["selected"][0]["title"])
    except Exception:
        selected_title = normalize_text(topic.topic)

    print("✅ Selected title:", selected_title)

    # 5) File naming (slug frozen here)
    post_date = date.today().isoformat()  # still used for filename + image folder
    published_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    slug = slugify(selected_title)
    filename = f"{post_date}-{slug}.md"
    file_path = ASTRO_POSTS_DIR / filename

    # Post slug used for images folder convention
    post_slug = f"{post_date}-{slug}"

    # 6) Frontmatter meta
    meta_description = f"Curated {topic.category.replace('_', ' ')} picks for {normalize_text(topic.audience)}."

    astro_products: list[dict] = []
    for p in products:
        astro_products.append({
            "title": p.get("title") or "",
            "url": p.get("url") or "https://www.amazon.com",
            "price": p.get("price") or "—",
            "rating": float(p.get("rating")) if p.get("rating") is not None else 0.0,
            "reviews_count": int(p.get("reviews_count")) if p.get("reviews_count") is not None else 0,
            "description": p.get("description") or "",
        })

    md: list[str] = []
    md.append("---")
    md.append(f'title: "{normalize_text(selected_title)}"')
    md.append(f'description: "{meta_description}"')
    md.append(f'publishedAt: "{published_at}"')
    md.append(f'category: "{topic.category}"')
    md.append(f'audience: "{normalize_text(topic.audience)}"')
    md.append(f"products: {json.dumps(astro_products, ensure_ascii=False)}")
    md.append("---")
    md.append("")

    # Canonical post skeleton (structure only)
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
        title = normalize_text(p.get("title", "")).strip() or f"Product {idx+1}"
        pick_id = _make_pick_anchor_id(title, idx)

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
    before_wc = estimate_word_count(draft_markdown)

    # 7) Depth expansion (UPGRADE MODE)
    depth_agent = DepthExpansionAgent()

    modules = [
        ExpansionModuleSpec(name="intro", enabled=True, max_words=140, rewrite_mode="upgrade"),
        ExpansionModuleSpec(name="how_we_chose", enabled=True, max_words=170, rewrite_mode="upgrade"),
        ExpansionModuleSpec(name="alternatives", enabled=True, max_words=220, rewrite_mode="upgrade"),
        ExpansionModuleSpec(name="product_writeups", enabled=True, max_words=900, rewrite_mode="upgrade"),
    ]

    depth_inp = DepthExpansionInput(
        draft_markdown=draft_markdown,
        products=products,
        modules=modules,
        rewrite_mode="upgrade",
        max_added_words=900,
        voice="neutral",
        faqs=[],
        forbid_claims_of_testing=True,
    )

    depth_out = depth_agent.run(depth_inp)
    final_markdown = depth_out.get("expanded_markdown", draft_markdown)
    after_wc = estimate_word_count(final_markdown)

    # 8) Extract final content and run final editorial title pass (slug remains frozen)
    intro_text = _extract_section(final_markdown, "Intro")
    picks_texts = _extract_picks(final_markdown)
    alternatives_text = _extract_section(final_markdown, "Alternatives worth considering")


    # Title max chars configurable for mobile
    max_chars = int(os.getenv("TITLE_MAX_CHARS", "60"))

    try:
        llm = OpenAIJsonLLM()
        final_title_agent = FinalTitleAgent(
            llm=llm,
            config=FinalTitleConfig(max_chars=max_chars),
        )
        final_title = final_title_agent.run(
            topic=normalize_text(topic.topic),
            category=topic.category,
            intro=intro_text or normalize_text(topic.topic),
            picks=picks_texts,
            products=products,
            alternatives=alternatives_text or None,
        )
        final_markdown = _replace_frontmatter_field(final_markdown, "title", final_title)
        print("✅ Final Title (post-body):", final_title)
    except Exception as e:
        # If title pass fails, keep original title
        print("⚠️ Final title pass unavailable, keeping initial title:", e)

    # 9) Hero image generation (first creation only, with placeholder fallback)
    alternatives_text = _extract_section(final_markdown, "Alternatives worth considering")

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
            category=topic.category,
            title=normalize_text(topic.topic),
            intro=intro_text or normalize_text(topic.topic),
            picks=picks_texts,
            alternatives=alternatives_text or None,
        )

        hero_image_url, hero_alt = hero.hero_image_path, hero.hero_alt
        print("✅ Hero image ready:", hero_image_url)

    except Exception as e:
        msg = str(e)
        if "Error code: 403" in msg and "must be verified" in msg:
            print("⚠️ Hero image generation gated (org verification required). Using placeholder.")
        else:
            print("⚠️ Hero image generation unavailable, using placeholder:", e)

        hero_image_url, hero_alt = _copy_placeholder_hero(post_slug)

    # Inject hero into frontmatter
    final_markdown = _replace_frontmatter_field(final_markdown, "heroImage", hero_image_url)
    final_markdown = _replace_frontmatter_field(final_markdown, "heroAlt", hero_alt)

    # Optional image credit fields
    if DEFAULT_IMAGE_CREDIT_NAME:
        final_markdown = _replace_frontmatter_field(final_markdown, "imageCreditName", DEFAULT_IMAGE_CREDIT_NAME)
    if DEFAULT_IMAGE_CREDIT_URL:
        final_markdown = _replace_frontmatter_field(final_markdown, "imageCreditUrl", DEFAULT_IMAGE_CREDIT_URL)

    # 10) Write post
    file_path.write_text(final_markdown, encoding="utf-8")
    print(f"✅ Astro post saved to {file_path}")

    # 11) Log
    append_log({
        "date": post_date,
        "title_initial": normalize_text(selected_title),
        "topic": normalize_text(topic.topic),
        "category": topic.category,
        "audience": normalize_text(topic.audience),
        "file": str(file_path).replace("\\", "/"),
        "product_count": len(products),
        "heroImage": hero_image_url,
        "word_count_before": before_wc,
        "word_count_after": after_wc,
        "depth_modules_applied": depth_out.get("applied_modules", []),
        "title_candidates_top3": (title_out.get("selected", [])[:3] if isinstance(title_out, dict) else []),
    })
    print(f"✅ Post logged in {LOG_PATH}")


if __name__ == "__main__":
    main()
