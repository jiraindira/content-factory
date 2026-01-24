from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class PostManifestPaths:
    dir: Path = Path("output/post_manifests")

    def for_post_slug(self, post_slug: str) -> Path:
        safe = post_slug.strip().replace("/", "-")
        return self.dir / f"{safe}.json"


def write_post_manifest(
    *,
    post_slug: str,
    provider: str,
    products: list[dict[str, Any]],
    manifest_paths: PostManifestPaths | None = None,
) -> Path:
    mp = manifest_paths or PostManifestPaths()
    mp.dir.mkdir(parents=True, exist_ok=True)

    items = []
    for p in products:
        items.append(
            {
                "pick_id": p.get("pick_id"),
                "generated_title": p.get("title"),
                "catalog_key": p.get("catalog_key"),
                "affiliate_url": p.get("url") if isinstance(p.get("url"), str) else "",
                "status": "ok",
                "notes": "",
            }
        )

    data = {
        "version": 1,
        "post_slug": post_slug,
        "provider": provider,
        "generated_at": _utc_now_iso(),
        "items": items,
        "instructions": "Fill in affiliate_url + optional corrections in the central catalog. Use status=not_found in the catalog to remove.",
    }

    path = mp.for_post_slug(post_slug)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
