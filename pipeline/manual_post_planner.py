from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(text: str) -> str:
    s = (text or "").lower().strip()
    s = s.replace("’", "").replace("'", "")
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _as_str(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def _as_float(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _as_int(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def _derive_topic(*, category: str, subcategory: str, audience: str) -> str:
    """
    Deterministic placeholder topic until TopicAgent exists.
    Keep it simple and stable.
    """
    cat = category.replace("_", " ").strip()
    sub = subcategory.replace("_", " ").strip()
    aud = audience.strip()
    if sub:
        return f"Best-selling {sub} picks ({cat}) for {aud}"
    return f"Best-selling {cat} picks for {aud}"


def _ensure_catalog_upsert(
    *,
    catalog_path: Path,
    provider: str,
    products: list[dict[str, Any]],
) -> int:
    """
    Minimal, dependency-free catalog upsert.

    - Creates catalog if missing
    - Adds missing items
    - Does NOT overwrite existing non-empty values (only fills blanks)
    Returns count of newly created items.
    """
    created = 0

    if catalog_path.exists():
        raw = catalog_path.read_text(encoding="utf-8").strip()
        if raw:
            catalog = json.loads(raw)
        else:
            catalog = {}
    else:
        catalog = {}

    if not isinstance(catalog, dict):
        catalog = {}

    version = int(catalog.get("version") or 1)
    items = catalog.get("items")
    if not isinstance(items, dict):
        items = {}
        catalog["items"] = items

    for p in products:
        key = _as_str(p.get("catalog_key"))
        title = _as_str(p.get("title"))
        if not key or not title:
            continue

        incoming = {
            "provider": provider,
            "status": _as_str(p.get("status") or "ok") or "ok",
            "title": title,
            "affiliate_url": _as_str(p.get("affiliate_url")),
            "rating": _as_float(p.get("rating")),
            "reviews_count": _as_int(p.get("reviews_count")),
            "price": _as_str(p.get("price")),
            # optional fields kept for forward-compat
            "asin": _as_str(p.get("asin")),
            "notes": _as_str(p.get("notes")),
        }

        existing = items.get(key)
        if not isinstance(existing, dict):
            items[key] = incoming
            created += 1
            continue

        # Fill blanks only (preserve anything already set)
        for k, v in incoming.items():
            if k not in existing or existing.get(k) in ("", None, 0, 0.0):
                # Only set if incoming is meaningful
                if v not in ("", None, 0, 0.0):
                    existing[k] = v

    catalog["version"] = version
    catalog["updated_at"] = _utc_now_iso()

    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    return created


@dataclass(frozen=True)
class ManualPlannerPaths:
    posts_dir: Path = Path("data/posts")
    # New default location (can still be overridden by env var)
    catalog_path: Path = Path(os.getenv("CATALOG_PATH", os.getenv("MANUAL_CATALOG_PATH", "data/catalog/master.json")))
    # New default input location
    input_path: Path = Path("data/inputs/manual/post_input.json")


@dataclass(frozen=True)
class ManualPlannerConfig:
    provider_id_default: str = "amazon_uk"
    format_id_default: str = "top_picks"
    min_picks_default: int = 6


class ManualPostPlanner:
    """
    Step 1 (manual pipeline, JSON-driven):

    Input: data/inputs/manual/post_input.json
      {
        "category": "...",
        "subcategory": "...",
        "audience": "...",
        "source_url": "...",
        "products": [
          {"name": "...", "url": "...", "rating": 4.6, "reviews_count": 1234, "price": "£..", "status": "ok"}
        ]
      }

    Output:
      - data/posts/<slug>.plan.json
      - data/posts/<slug>.draft.md
      - upserts product facts into data/catalog/master.json (fills blanks only)
    """

    def __init__(
        self,
        *,
        paths: ManualPlannerPaths | None = None,
        config: ManualPlannerConfig | None = None,
        logger=print,
    ):
        self.paths = paths or ManualPlannerPaths()
        self.config = config or ManualPlannerConfig()
        self._log = logger

    def _load_input(self, *, input_path: Path) -> dict[str, Any]:
        if not input_path.exists():
            raise FileNotFoundError(f"Missing input JSON: {input_path}")
        raw = _read_json(input_path)
        if not isinstance(raw, dict):
            raise ValueError(f"Input JSON must be an object: {input_path}")
        return raw

    def _normalize_products(
        self,
        *,
        provider_id: str,
        products_raw: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(products_raw, list):
            raise ValueError("Input JSON field 'products' must be a list.")

        out: list[dict[str, Any]] = []
        for it in products_raw:
            if not isinstance(it, dict):
                continue
            status = (_as_str(it.get("status")) or "ok").lower()
            if status not in {"ok", "not_found"}:
                status = "ok"

            name = _as_str(it.get("name"))
            url = _as_str(it.get("url"))
            if not name:
                continue

            # keep even if url missing (you might fill it later), but prefer completeness
            out.append(
                {
                    "status": status,
                    "title": name,
                    "affiliate_url": url,
                    "rating": _as_float(it.get("rating")),
                    "reviews_count": _as_int(it.get("reviews_count")),
                    "price": _as_str(it.get("price")),
                    "amazon_search_query": it.get("amazon_search_query"),
                    "catalog_key": f"{provider_id}:{_slugify(name)}",
                }
            )
        return out

    def run(
        self,
        *,
        date: str,
        input_path: str | None = None,
        provider_id: str | None = None,
        format_id: str | None = None,
        min_picks: int | None = None,
    ) -> dict[str, Any]:
        provider_id = (provider_id or self.config.provider_id_default).strip()
        format_id = (format_id or self.config.format_id_default).strip()
        min_picks = int(min_picks or self.config.min_picks_default)

        ipath = Path(input_path) if input_path else self.paths.input_path
        inp = self._load_input(input_path=ipath)

        category = _as_str(inp.get("category")) or "general"
        subcategory = _as_str(inp.get("subcategory"))
        audience = _as_str(inp.get("audience")) or "UK readers"
        source_url = _as_str(inp.get("source_url"))

        products_all = self._normalize_products(provider_id=provider_id, products_raw=inp.get("products"))
        products_ok = [p for p in products_all if (p.get("status") or "ok") == "ok"]

        if len(products_ok) < min_picks:
            raise RuntimeError(f"Only {len(products_ok)} usable products (status=ok). Need at least {min_picks}.")

        # topic/title placeholder (agents will replace later)
        topic_text = _derive_topic(category=category, subcategory=subcategory, audience=audience)

        slug = f"{date}-{_slugify(topic_text)}"
        plan_path = self.paths.posts_dir / f"{slug}.plan.json"
        draft_path = self.paths.posts_dir / f"{slug}.draft.md"

        # Add pick_id and limit to min_picks (keep order from input)
        products_out: list[dict[str, Any]] = []
        for idx, p in enumerate(products_ok[:min_picks], start=1):
            title = _as_str(p.get("title"))
            pick_id = f"pick-{idx}-{_slugify(title)}"
            products_out.append(
                {
                    "pick_id": pick_id,
                    "catalog_key": p.get("catalog_key") or "",
                    "title": title,
                    "description": _as_str(p.get("description") or ""),
                    "affiliate_url": _as_str(p.get("affiliate_url")),
                    "price": _as_str(p.get("price")),
                    "rating": _as_float(p.get("rating")),
                    "reviews_count": _as_int(p.get("reviews_count")),
                    "amazon_search_query": p.get("amazon_search_query"),
                    "status": "ok",
                }
            )

        # Upsert into catalog (fills blanks only)
        created = _ensure_catalog_upsert(
            catalog_path=self.paths.catalog_path,
            provider=provider_id,
            products=products_out,
        )

        self._log(f"🟢 Step 1: plan post date={date} slug={slug}")
        self._log(f"📥 Input: {ipath}")
        self._log(f"📘 Catalog: {self.paths.catalog_path} (created {created} new items)")
        self._log(f"🧺 Picks: {len(products_out)}")

        plan: dict[str, Any] = {
            "version": 1,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "status": "planned",
            "provider_id": provider_id,
            "format_id": format_id,
            "source_url": source_url,
            "topic": topic_text,
            "draft_title": topic_text,
            "category": category,
            "subcategory": subcategory,
            "audience": audience,
            "products": products_out,
        }
        _write_json(plan_path, plan)

        # Draft scaffold
        md: list[str] = []
        md.append(f"# {topic_text}")
        md.append("")
        md.append("> Draft scaffold (manual pipeline). Step 3 writes the final Astro markdown.")
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
        for p in products_out:
            md.append(f"<!-- pick_id: {p['pick_id']} -->")
            md.append(f"### {p['title']}")
            md.append("")
            md.append(f"{{{{PICK:{p['pick_id']}}}}}")
            md.append("")
            md.append("<hr />")
            md.append("")
        md.append("## Alternatives worth considering")
        md.append("")
        md.append("{{ALTERNATIVES}}")
        md.append("")

        self.paths.posts_dir.mkdir(parents=True, exist_ok=True)
        draft_path.write_text("\n".join(md), encoding="utf-8")

        self._log(f"📄 Plan: {plan_path}")
        self._log(f"📝 Draft: {draft_path}")
        return {"slug": slug, "plan_path": str(plan_path), "draft_path": str(draft_path)}
