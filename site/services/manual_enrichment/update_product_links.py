from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple, List, Optional

import yaml


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


@dataclass
class UpdateStats:
    files_scanned: int = 0
    files_updated: int = 0
    products_seen: int = 0
    products_updated: int = 0
    products_missing_mapping: int = 0


def parse_md(text: str) -> Tuple[Dict[str, Any], str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_raw = m.group(1)
    body = m.group(2)
    fm = yaml.safe_load(fm_raw) or {}
    if not isinstance(fm, dict):
        raise ValueError("Frontmatter must be a YAML object")
    return fm, body


def dump_md(frontmatter: Dict[str, Any], body: str) -> str:
    fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{fm_yaml}\n---\n{body.lstrip()}"


def _to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.strip().replace(",", "")
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _to_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return int(x)
    if isinstance(x, float):
        return int(x)
    if isinstance(x, str):
        s = x.strip().replace(",", "")
        if not s:
            return None
        s = re.sub(r"[^\d]", "", s)
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return None
    return None


def load_mapping(path: Path) -> Dict[str, Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manual_product_links.json must be a JSON object keyed by product title")

    out: Dict[str, Dict[str, Any]] = {}
    for title, entry in data.items():
        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(entry, dict):
            continue

        url = str(entry.get("url") or "").strip()
        asin = str(entry.get("asin") or "").strip()

        rating = _to_float(entry.get("rating"))
        reviews_count = _to_int(entry.get("reviews_count"))

        out[title.strip()] = {
            "url": url,
            "asin": asin,
            "rating": rating,
            "reviews_count": reviews_count,
        }

    return out


def update_posts(posts_dir: Path, mapping_path: Path, dry_run: bool) -> UpdateStats:
    mapping = load_mapping(mapping_path)
    stats = UpdateStats()

    files: List[Path] = []
    files.extend(posts_dir.rglob("*.md"))
    files.extend(posts_dir.rglob("*.mdx"))

    for fp in files:
        stats.files_scanned += 1
        text = fp.read_text(encoding="utf-8")
        fm, body = parse_md(text)

        products = fm.get("products")
        if not isinstance(products, list) or not products:
            continue

        changed = False

        for p in products:
            if not isinstance(p, dict):
                continue

            title = str(p.get("title") or "").strip()
            if not title:
                continue

            stats.products_seen += 1
            entry = mapping.get(title)
            if not entry:
                stats.products_missing_mapping += 1
                continue

            # URL (required for affiliate)
            url = str(entry.get("url") or "").strip()
            if url and str(p.get("url") or "").strip() != url:
                p["url"] = url
                changed = True
                stats.products_updated += 1

            # ASIN (optional)
            asin = str(entry.get("asin") or "").strip()
            if asin and str(p.get("asin") or "").strip() != asin:
                p["asin"] = asin
                changed = True

            # Rating (optional but supported)
            rating = entry.get("rating")
            if isinstance(rating, (int, float)) and rating > 0:
                current = _to_float(p.get("rating")) or 0.0
                if abs(current - float(rating)) > 1e-9:
                    p["rating"] = float(rating)
                    changed = True

            # Reviews count (optional but supported)
            reviews_count = entry.get("reviews_count")
            if isinstance(reviews_count, int) and reviews_count > 0:
                # Write canonical field
                current_rc = _to_int(p.get("reviews_count")) or 0
                if current_rc != reviews_count:
                    p["reviews_count"] = reviews_count
                    changed = True

                # Backward compatibility: if old singular exists, keep it in sync
                if "review_count" in p:
                    current_singular = _to_int(p.get("review_count")) or 0
                    if current_singular != reviews_count:
                        p["review_count"] = reviews_count
                        changed = True

        if changed:
            fm["products"] = products
            new_text = dump_md(fm, body)
            if not dry_run:
                fp.write_text(new_text, encoding="utf-8")
            stats.files_updated += 1

    return stats


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Update product URLs/ASINs/ratings/review counts in Astro post frontmatter using a manual mapping file."
    )
    parser.add_argument("--posts-dir", default="src/content/posts", help="Directory containing markdown posts")
    parser.add_argument("--mapping", default="data/manual_product_links.json", help="Path to mapping JSON")
    parser.add_argument("--dry-run", action="store_true", help="Do not write files")
    args = parser.parse_args()

    posts_dir = Path(args.posts_dir)
    mapping_path = Path(args.mapping)

    if not posts_dir.exists():
        raise SystemExit(f"Posts dir not found: {posts_dir}")
    if not mapping_path.exists():
        raise SystemExit(f"Mapping file not found: {mapping_path}")

    stats = update_posts(posts_dir, mapping_path, args.dry_run)
    print(f"Scanned: {stats.files_scanned} files")
    print(f"Updated: {stats.files_updated} files" + (" (dry-run)" if args.dry_run else ""))
    print(f"Products seen: {stats.products_seen}")
    print(f"Products updated: {stats.products_updated}")
    print(f"Missing mapping entries: {stats.products_missing_mapping}")


if __name__ == "__main__":
    main()
