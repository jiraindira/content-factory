from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.product_catalog import ProductCatalog


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


@dataclass(frozen=True)
class ManualCatalogApplierPaths:
    posts_dir: Path = Path("data/posts")
    catalog_path: Path = Path(os.getenv("MANUAL_CATALOG_PATH", "output/catalog/manual_product_catalog.json"))


@dataclass(frozen=True)
class ManualCatalogApplierConfig:
    min_picks_default: int = 6


class ManualCatalogApplier:
    """
    Step 2 (manual pipeline):

    - loads plan json
    - hydrates products from the manual catalog
    - prunes products marked not_found
    - enforces min_picks (fails fast if you removed too many)
    - writes plan json back (in-place)
    """

    def __init__(
        self,
        *,
        paths: ManualCatalogApplierPaths | None = None,
        config: ManualCatalogApplierConfig | None = None,
        logger=print,
    ) -> None:
        self.paths = paths or ManualCatalogApplierPaths()
        self.config = config or ManualCatalogApplierConfig()
        self._log = logger

    def run(self, *, post_slug: str, min_picks: int | None = None) -> dict[str, Any]:
        min_picks = int(min_picks or self.config.min_picks_default)

        plan_path = self.paths.posts_dir / f"{post_slug}.plan.json"
        if not plan_path.exists():
            raise FileNotFoundError(f"Missing plan: {plan_path}. Run Step 1 first.")

        plan = _read_json(plan_path)
        provider_id = str(plan.get("provider_id") or "").strip()
        if not provider_id:
            raise RuntimeError("Plan missing provider_id.")

        products = plan.get("products", [])
        if not isinstance(products, list) or not products:
            raise RuntimeError("Plan has no products.")

        catalog = ProductCatalog(path=self.paths.catalog_path)

        hydrated, removed = catalog.apply_to_products(provider=provider_id, products=products)

        # Convert 'url' key from catalog hydrator into plan's expected 'affiliate_url' field.
        normalized: list[dict[str, Any]] = []
        for p in hydrated:
            if not isinstance(p, dict):
                continue
            p2 = dict(p)
            if "url" in p2 and "affiliate_url" not in p2:
                p2["affiliate_url"] = p2.get("url") or ""
            normalized.append(p2)

        usable = []
        for p in normalized:
            # Only keep items that have at least a title and (optionally) a URL if available.
            title = str(p.get("title") or "").strip()
            if not title:
                continue
            usable.append(p)

        if len(usable) < min_picks:
            # Fail fast: user removed too many items from catalog or marked them not_found.
            raise RuntimeError(
                f"{post_slug}.plan.json: only {len(usable)} usable picks remain after pruning "
                f"(min required: {min_picks}). Fix catalog or re-plan the post."
            )

        plan["products"] = usable
        plan["updated_at"] = _utc_now_iso()
        plan["status"] = "catalog_applied"
        plan["status_updated_at"] = _utc_now_iso()
        plan["status_meta"] = {
            "min_picks": min_picks,
            "removed_count": len(removed),
            "catalog_path": str(self.paths.catalog_path),
        }

        _write_json(plan_path, plan)

        self._log(f"🟣 Step 2: apply catalog slug={post_slug}")
        self._log(f"📘 Catalog: {self.paths.catalog_path}")
        self._log(f"🧺 Picks: {len(usable)} (removed {len(removed)})")
        self._log(f"📄 Updated plan: {plan_path}")

        return {"post_slug": post_slug, "plan_path": str(plan_path), "removed": removed, "usable_count": len(usable)}
