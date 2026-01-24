from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable, Tuple

from lib.product_catalog import ProductCatalog


CATALOG_PATH = Path("data/catalog/master.json")
POSTS_DIR = Path("data/posts")

TOKEN_RE = re.compile(r"\{catalog:(?P<key>[^:}]+):(?P<field>[^}]+)\}")

# Matches a single pick block in the draft template:
# <!-- pick_id: ... catalog_key: SOME_KEY -->
# ...content...
# <hr />
#
# We remove the entire block if SOME_KEY is pruned.
PICK_BLOCK_RE = re.compile(
    r"(?ms)^\s*<!--\s*pick_id:\s*(?P<pick_id>[^ ]+)\s+catalog_key:\s*(?P<key>[^ ]+)\s*-->\s*\n"
    r".*?\n^\s*<hr\s*/>\s*$\n?",
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Step 2 (manual pipeline): hydrate plan + draft from data/catalog/master.json, prune invalid picks."
    )
    p.add_argument("--post-slug", default="", help="Optional: apply only to one post slug")
    p.add_argument("--min-picks", type=int, default=5, help="Fail if fewer than this many picks remain (default: 6)")
    return p.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _catalog_value(item: dict[str, Any], field: str) -> str:
    if field == "affiliate_url":
        return str(item.get("affiliate_url") or "")
    if field == "rating":
        v = item.get("rating")
        try:
            return f"{float(v):.1f}" if v is not None else ""
        except Exception:
            return ""
    if field == "reviews_count":
        v = item.get("reviews_count")
        try:
            return str(int(v)) if v is not None else ""
        except Exception:
            return ""
    if field == "price":
        return str(item.get("price") or "")
    if field == "asin":
        return str(item.get("asin") or "")
    if field == "title":
        return str(item.get("title") or "")
    if field == "status":
        return str(item.get("status") or "")
    return ""


def _hydrate_text(text: str, catalog_items: dict[str, dict[str, Any]]) -> str:
    def repl(m: re.Match[str]) -> str:
        key = m.group("key")
        field = m.group("field")
        item = catalog_items.get(key)
        if not isinstance(item, dict):
            return ""
        return _catalog_value(item, field)

    return TOKEN_RE.sub(repl, text)


def _plan_files(post_slug: str | None) -> Iterable[Tuple[Path, Path]]:
    if post_slug:
        plan = POSTS_DIR / f"{post_slug}.plan.json"
        draft = POSTS_DIR / f"{post_slug}.draft.md"
        if plan.exists() and draft.exists():
            yield (plan, draft)
        return

    for plan in sorted(POSTS_DIR.glob("*.plan.json")):
        slug = plan.name.replace(".plan.json", "")
        draft = POSTS_DIR / f"{slug}.draft.md"
        if draft.exists():
            yield (plan, draft)


def _is_pick_usable(item: dict[str, Any]) -> bool:
    # Recommendation: prune anything missing, non-ok, or without a link
    status = str(item.get("status") or "").strip().lower()
    if status and status != "ok":
        return False
    affiliate_url = str(item.get("affiliate_url") or "").strip()
    if not affiliate_url:
        return False
    return True


def _prune_plan_products(
    plan: dict[str, Any],
    catalog_items: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Returns (kept_products, pruned_catalog_keys)."""
    products = plan.get("products", [])
    if not isinstance(products, list):
        return [], []

    kept: list[dict[str, Any]] = []
    pruned_keys: list[str] = []

    for p in products:
        if not isinstance(p, dict):
            continue
        key = str(p.get("catalog_key") or "").strip()
        if not key:
            pruned_keys.append(key)
            continue

        item = catalog_items.get(key)
        if not isinstance(item, dict):
            pruned_keys.append(key)
            continue

        if not _is_pick_usable(item):
            pruned_keys.append(key)
            continue

        kept.append(p)

    return kept, pruned_keys


def _remove_pruned_blocks_from_draft(draft_text: str, pruned_keys: set[str]) -> str:
    if not pruned_keys:
        return draft_text

    def repl(m: re.Match[str]) -> str:
        key = m.group("key").strip()
        return "" if key in pruned_keys else m.group(0)

    out = PICK_BLOCK_RE.sub(repl, draft_text)

    # Clean up excessive blank lines introduced by deletions
    out = re.sub(r"\n{4,}", "\n\n\n", out)
    return out.strip() + "\n"


def main() -> int:
    args = parse_args()
    POSTS_DIR.mkdir(parents=True, exist_ok=True)

    catalog = ProductCatalog(path=CATALOG_PATH)
    data = catalog.load()
    catalog_items = data.get("items", {})
    if not isinstance(catalog_items, dict):
        catalog_items = {}

    updated_count = 0

    for plan_path, draft_path in _plan_files(args.post_slug.strip() or None):
        plan = _load_json(plan_path)

        # 1) Prune products in the plan based on catalog usability
        kept_products, pruned_keys_list = _prune_plan_products(plan, catalog_items)
        pruned_keys = set(k for k in pruned_keys_list if k)

        plan["products"] = kept_products

        # Fail fast if too few remain
        if len(kept_products) < int(args.min_picks):
            raise RuntimeError(
                f"{plan_path.name}: only {len(kept_products)} usable picks remain after pruning "
                f"(min required: {args.min_picks}). Fix catalog or re-plan the post."
            )

        # 2) Hydrate remaining products in plan from catalog
        for p in kept_products:
            if not isinstance(p, dict):
                continue
            key = str(p.get("catalog_key") or "")
            item = catalog_items.get(key)
            if not isinstance(item, dict):
                continue

            p["affiliate_url"] = str(item.get("affiliate_url") or "")
            p["price"] = str(item.get("price") or "")
            p["asin"] = str(item.get("asin") or "")
            try:
                p["rating"] = float(item.get("rating") or 0.0)
            except Exception:
                p["rating"] = 0.0
            try:
                p["reviews_count"] = int(item.get("reviews_count") or 0)
            except Exception:
                p["reviews_count"] = 0

        _write_json(plan_path, plan)

        # 3) Update draft: remove pruned pick blocks, then hydrate tokens
        draft_text = draft_path.read_text(encoding="utf-8")
        draft_text = _remove_pruned_blocks_from_draft(draft_text, pruned_keys)
        hydrated = _hydrate_text(draft_text, catalog_items)
        draft_path.write_text(hydrated, encoding="utf-8")

        updated_count += 1
        pruned_msg = f" (pruned {len(pruned_keys)} picks)" if pruned_keys else ""
        print(f"✅ Hydrated: {plan_path.name} + {draft_path.name}{pruned_msg}")

    if updated_count == 0:
        print("⚠️ Nothing updated (no matching plan/draft pairs found).")

    print(f"📚 Catalog used: {CATALOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
