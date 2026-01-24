from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from lib.product_catalog import ProductCatalog

CATALOG_PATH = Path("output/catalog/manual_product_catalog.json")

PICK_MARK_RE = re.compile(r"<!--\s*pick_id:\s*([a-z0-9\-_:]+)\s*-->", re.IGNORECASE)
H3_RE = re.compile(r"^###\s+(.+?)\s*$")


def _split_frontmatter(md: str) -> tuple[dict[str, Any], str, str]:
    """
    Returns (frontmatter_dict, frontmatter_raw, body_raw)
    frontmatter_raw includes the --- blocks (exactly as found)
    """
    text = md.lstrip("\ufeff")
    if not text.startswith("---"):
        return {}, "", md

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, "", md

    _, fm_raw, rest = parts[0], parts[1], parts[2]
    fm_block = f"---{fm_raw}---"
    fm_text = fm_raw.strip()

    # naive YAML-ish frontmatter parsing for our known keys:
    # We only need products JSON line safely.
    frontmatter: dict[str, Any] = {}
    lines = fm_text.splitlines()
    for line in lines:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip()
        if k == "products":
            try:
                frontmatter["products"] = json.loads(v)
            except Exception:
                frontmatter["products"] = []
        else:
            # keep raw strings if needed
            frontmatter[k] = v.strip().strip('"')

    return frontmatter, fm_block, rest.lstrip("\n")


def _rebuild_frontmatter(fm_block: str, new_products: list[dict[str, Any]]) -> str:
    """
    Replace only the 'products:' line with new JSON.
    Keep everything else identical.
    """
    lines = fm_block.splitlines()
    out = []
    replaced = False
    for line in lines:
        if line.strip().startswith("products:"):
            out.append("products: " + json.dumps(new_products, ensure_ascii=False))
            replaced = True
        else:
            out.append(line)
    if not replaced:
        # insert before closing ---
        if out and out[-1].strip() == "---":
            out.insert(len(out) - 1, "products: " + json.dumps(new_products, ensure_ascii=False))
        else:
            out.append("products: " + json.dumps(new_products, ensure_ascii=False))
    return "\n".join(out)


def _remove_pick_sections(body: str, remove_pick_ids: set[str]) -> str:
    """
    Removes sections starting at <!-- pick_id: X --> up to (but excluding) the next pick marker,
    or end of document.
    """
    if not remove_pick_ids:
        return body

    lines = body.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        m = PICK_MARK_RE.search(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue

        pick_id = m.group(1).strip()
        if pick_id not in remove_pick_ids:
            out.append(lines[i])
            i += 1
            continue

        # Skip this marker and everything until next marker
        i += 1
        while i < len(lines):
            if PICK_MARK_RE.search(lines[i]):
                break
            i += 1
        # do not include skipped lines
    return "\n".join(out).strip() + "\n"


def _rename_pick_headings(body: str, title_by_pick_id: dict[str, str]) -> str:
    """
    For each pick marker, rename the immediately following H3 to the catalog title (if provided).
    """
    lines = body.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = PICK_MARK_RE.search(line)
        out.append(line)
        if not m:
            i += 1
            continue

        pick_id = m.group(1).strip()
        new_title = title_by_pick_id.get(pick_id)
        if not new_title:
            i += 1
            continue

        # Find next H3 after marker
        j = i + 1
        while j < len(lines):
            if lines[j].strip() == "":
                j += 1
                continue
            h3m = H3_RE.match(lines[j])
            if h3m:
                out.append(f"### {new_title}")
                # skip original H3 line
                j += 1
                # copy rest until j catches up
                i = j
                break
            else:
                # if next non-empty isn't H3, bail
                i += 1
                break
        else:
            i += 1
    return "\n".join(out).strip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--post", required=True, help="Path to markdown post file under site/src/content/posts")
    ap.add_argument("--provider", default="amazon_uk", help="Provider id (default amazon_uk)")
    args = ap.parse_args()

    post_path = Path(args.post)
    if not post_path.exists():
        raise SystemExit(f"Post not found: {post_path}")

    md = post_path.read_text(encoding="utf-8")
    fm, fm_block, body = _split_frontmatter(md)

    products = fm.get("products", [])
    if not isinstance(products, list):
        products = []

    # require pick_id present
    products2: list[dict[str, Any]] = []
    for p in products:
        if not isinstance(p, dict):
            continue
        products2.append(p)

    catalog = ProductCatalog(path=CATALOG_PATH)
    hydrated, removed_meta = catalog.apply_to_products(provider=args.provider, products=products2)

    remove_ids = {str(x.get("pick_id")) for x in removed_meta if x.get("pick_id")}
    title_by_pick_id = {str(p.get("pick_id")): str(p.get("title")) for p in hydrated if p.get("pick_id") and p.get("title")}

    body2 = body
    body2 = _remove_pick_sections(body2, remove_pick_ids=remove_ids)
    body2 = _rename_pick_headings(body2, title_by_pick_id=title_by_pick_id)

    fm_new = _rebuild_frontmatter(fm_block, hydrated)
    out_md = fm_new.strip() + "\n\n" + body2

    post_path.write_text(out_md, encoding="utf-8")
    print(f"✅ Hydrated post updated: {post_path}")
    if removed_meta:
        print(f"🗑️ Removed {len(removed_meta)} product sections due to catalog status=not_found")


if __name__ == "__main__":
    main()
