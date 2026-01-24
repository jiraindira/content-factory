from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypedDict


CatalogStatus = Literal["ok", "not_found", "replace"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify_heading(text: str) -> str:
    return (
        str(text or "")
        .lower()
        .strip()
        .replace("’", "")
        .replace("'", "")
    )


def slugify_key(text: str) -> str:
    s = slugify_heading(text)
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


class CatalogItem(TypedDict, total=False):
    provider: str
    status: CatalogStatus
    title: str
    affiliate_url: str
    rating: float
    reviews_count: int
    price: str
    asin: str
    notes: str
    replace_with: str  # another catalog_key


class CatalogFile(TypedDict):
    version: int
    updated_at: str
    items: dict[str, CatalogItem]


@dataclass(frozen=True)
class CatalogMatch:
    catalog_key: str
    item: CatalogItem


class ProductCatalog:
    """
    Central, manual product catalog used to "hydrate" AI-suggested products
    into real affiliate links + accurate metadata.

    Key behaviors:
    - load(): ensures file exists and returns normalized structure
    - save(data=None): writes updated catalog; if data omitted, saves current on-disk normalized data
    - ensure_entries_for_products(): creates skeleton entries for new products
    - apply_to_products(): hydrates/removes/replaces products based on catalog
    """

    def __init__(self, *, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def _normalize(self, raw: Any) -> CatalogFile:
        if not isinstance(raw, dict):
            return {"version": 1, "updated_at": _utc_now_iso(), "items": {}}

        items = raw.get("items")
        if not isinstance(items, dict):
            items = {}

        return {
            "version": int(raw.get("version", 1)),
            "updated_at": str(raw.get("updated_at", _utc_now_iso())),
            "items": items,
        }

    def load(self) -> dict:
        """
        Loads the catalog JSON. If the file is missing or empty, returns a valid empty catalog structure.
        Never raises JSONDecodeError for an empty file.
        """
        if not self._path.exists():
            return {"version": 1, "items": {}}

        text = self._path.read_text(encoding="utf-8").strip()
        if not text:
            return {"version": 1, "items": {}}

        raw = json.loads(text)
        if not isinstance(raw, dict):
            return {"version": 1, "items": {}}

        raw.setdefault("version", 1)
        raw.setdefault("items", {})
        if not isinstance(raw.get("items"), dict):
            raw["items"] = {}

        return raw


    def save(self, data: CatalogFile | None = None) -> None:
        """
        Persist the catalog.

        Backward-compatible:
        - Existing callers can still call save(data)
        - If someone calls save() with no args, we write a normalized copy of what's on disk
          (prevents crashes and keeps file structure stable).
        """
        if data is None:
            data = self.load()
        else:
            data = self._normalize(data)

        data["updated_at"] = _utc_now_iso()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def default_catalog_key(self, *, provider: str, title: str) -> str:
        return f"{provider}:{slugify_key(title)}"

    def match(self, *, provider: str, title: str) -> CatalogMatch | None:
        data = self.load()
        key = self.default_catalog_key(provider=provider, title=title)
        item = data["items"].get(key)
        if isinstance(item, dict):
            return CatalogMatch(catalog_key=key, item=item)
        return None

    def ensure_entries_for_products(
        self,
        *,
        provider: str,
        products: list[dict[str, Any]],
    ) -> int:
        """
        Ensure the catalog contains skeleton entries for all products.

        Returns:
          number_of_new_items_created

        Skeleton entries let you manually fill:
          affiliate_url, rating, reviews_count, price, asin, notes, etc.
        """
        data = self.load()
        items = data.get("items", {})
        if not isinstance(items, dict):
            items = {}
            data["items"] = items

        created = 0

        for p in products or []:
            title = str(p.get("title") or "").strip()
            if not title:
                continue

            key = str(p.get("catalog_key") or "").strip()
            if not key:
                key = self.default_catalog_key(provider=provider, title=title)

            if key in items:
                continue

            items[key] = {
                "provider": provider,
                "status": "ok",
                "title": title,
                "affiliate_url": "",
                "rating": 0.0,
                "reviews_count": 0,
                "price": "",
                "asin": "",
                "notes": "",
            }
            created += 1

        if created:
            self.save(data)

        return created

    def upsert_item(self, *, catalog_key: str, item: CatalogItem) -> None:
        """
        Convenience: add or update a specific catalog item.
        """
        data = self.load()
        if not isinstance(data.get("items"), dict):
            data["items"] = {}
        data["items"][catalog_key] = item
        self.save(data)

    def apply_to_products(
        self,
        *,
        provider: str,
        products: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Returns (updated_products, removed_products_meta)

        Each product should contain:
          - pick_id: str
          - title: str
          - url/price/rating/reviews_count optional
          - catalog_key optional (we will compute if missing)
        """
        data = self.load()
        updated: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []

        for p in products or []:
            title = str(p.get("title") or "").strip()
            if not title:
                updated.append(p)
                continue

            key = str(p.get("catalog_key") or "").strip()
            if not key:
                key = self.default_catalog_key(provider=provider, title=title)

            item = data["items"].get(key)

            if not isinstance(item, dict):
                p2 = dict(p)
                p2["catalog_key"] = key
                updated.append(p2)
                continue

            status: str = str(item.get("status", "ok"))

            if status == "replace":
                replace_with = str(item.get("replace_with") or "").strip()
                if replace_with and replace_with in data["items"]:
                    item = data["items"][replace_with]
                    key = replace_with
                    status = str(item.get("status", "ok"))
                else:
                    p2 = dict(p)
                    p2["catalog_key"] = key
                    updated.append(p2)
                    continue

            if status == "not_found":
                removed.append({"pick_id": p.get("pick_id"), "catalog_key": key, "title": title})
                continue

            p2 = dict(p)
            p2["catalog_key"] = key

            if item.get("title"):
                p2["title"] = str(item["title"])
            if item.get("affiliate_url"):
                p2["url"] = str(item["affiliate_url"])
            if item.get("price"):
                p2["price"] = str(item["price"])

            if item.get("rating") is not None:
                try:
                    p2["rating"] = float(item["rating"])
                except Exception:
                    pass

            if item.get("reviews_count") is not None:
                try:
                    p2["reviews_count"] = int(item["reviews_count"])
                except Exception:
                    pass

            updated.append(p2)

        return updated, removed
