from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
import importlib

import yaml

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


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


def _import_product_catalog_class():
    """
    We try a few likely module paths so you don't have to refactor immediately.
    If your ProductCatalog lives elsewhere, pass --catalog-module.
    """
    candidates = [
        # Add your real path here if you know it.
        "product_catalog",
        "catalog",
        "src.product_catalog",
        "src.catalog",
        "app.product_catalog",
        "app.catalog",
    ]

    for mod in candidates:
        try:
            m = importlib.import_module(mod)
            if hasattr(m, "ProductCatalog"):
                return getattr(m, "ProductCatalog")
        except Exception:
            continue

    return None


def _load_product_catalog_class(explicit_module: str | None):
    if explicit_module:
        m = importlib.import_module(explicit_module)
        if not hasattr(m, "ProductCatalog"):
            raise RuntimeError(f"Module '{explicit_module}' does not export ProductCatalog")
        return getattr(m, "ProductCatalog")

    cls = _import_product_catalog_class()
    if cls is None:
        raise RuntimeError(
            "Could not import ProductCatalog.\n"
            "Fix by either:\n"
            "  1) Passing --catalog-module <python.module.path>, e.g. --catalog-module src.lib.product_catalog\n"
            "  2) Or adding your module path to the candidates list in hydrate_posts_from_catalog.py\n"
        )
    return cls


def hydrate_file(
    *,
    path: Path,
    catalog,
    provider: str,
    dry_run: bool,
    remove_not_found: bool,
) -> bool:
    """
    Returns True if file changed.
    """
    text = path.read_text(encoding="utf-8")
    fm, body = parse_md(text)

    products = fm.get("products")
    if not isinstance(products, list) or not products:
        return False

    updated_products, removed_meta = catalog.apply_to_products(provider=provider, products=products)

    if remove_not_found and removed_meta:
        # apply_to_products already omitted "not_found" ones from updated_products
        pass

    # If nothing changed structurally, avoid rewrite.
    if updated_products == products:
        return False

    fm["products"] = updated_products
    new_text = dump_md(fm, body)

    if not dry_run:
        path.write_text(new_text, encoding="utf-8")

    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hydrate existing Astro posts from the central ProductCatalog (no regeneration)."
    )
    parser.add_argument(
        "--posts-dir",
        default="site/src/content/posts",
        help="Directory containing markdown posts (md/mdx). Default: site/src/content/posts",
    )
    parser.add_argument(
        "--catalog-path",
        default="output/catalog/manual_product_catalog.json",
        help="Path to the central product catalog JSON file. Default: output/manual_product_catalog.json",
    )
    parser.add_argument(
        "--provider",
        default="amazon_uk",
        help="Provider key to use when matching catalog entries. Default: amazon_uk",
    )
    parser.add_argument(
        "--catalog-module",
        default=None,
        help="Python module path where ProductCatalog lives (if auto-detect fails). Example: src.lib.product_catalog",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write files, just report what would change.",
    )
    parser.add_argument(
        "--remove-not-found",
        action="store_true",
        help="If set, products marked not_found will be removed (default behavior already omits them).",
    )

    args = parser.parse_args()

    posts_dir = Path(args.posts_dir)
    catalog_path = Path(args.catalog_path)

    if not posts_dir.exists():
        raise SystemExit(f"Posts dir not found: {posts_dir}")
    if not catalog_path.exists():
        raise SystemExit(f"Catalog file not found: {catalog_path}")

    ProductCatalog = _load_product_catalog_class(args.catalog_module)
    catalog = ProductCatalog(path=catalog_path)

    files: List[Path] = []
    files.extend(posts_dir.rglob("*.md"))
    files.extend(posts_dir.rglob("*.mdx"))

    if not files:
        raise SystemExit(f"No .md or .mdx files found under {posts_dir}")

    changed = 0
    scanned = 0
    for fp in files:
        scanned += 1
        try:
            did_change = hydrate_file(
                path=fp,
                catalog=catalog,
                provider=args.provider,
                dry_run=args.dry_run,
                remove_not_found=args.remove_not_found,
            )
            if did_change:
                changed += 1
        except Exception as e:
            print(f"[WARN] Failed to hydrate {fp}: {e}")

    print(f"Scanned: {scanned} files")
    print(f"Updated: {changed} files" + (" (dry-run)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
