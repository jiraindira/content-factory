from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import yaml


@dataclass(frozen=True)
class OnboardPaths:
    brand_path: Path
    request_path: Path


def _ensure_nonempty(value: str, field_name: str) -> str:
    v = (value or "").strip()
    if not v:
        raise ValueError(f"{field_name} must not be empty")
    return v


def scaffold_brand_profile_dict(
    *,
    brand_id: str,
    domains_supported: Iterable[str],
    domain_primary: str,
) -> dict:
    brand_id = _ensure_nonempty(brand_id, "brand_id")
    domain_primary = _ensure_nonempty(domain_primary, "domain_primary")
    domains_supported = [d.strip() for d in domains_supported if (d or "").strip()]
    if not domains_supported:
        raise ValueError("domains_supported must not be empty")
    if domain_primary not in domains_supported:
        domains_supported = [domain_primary] + [d for d in domains_supported if d != domain_primary]

    # Scaffold is intentionally conservative: valid shape, placeholder values.
    return {
        "brand_id": brand_id,
        "brand_archetype": "trusted_guide",
        "brand_sources": {
            "require_at_least_one_of_purposes": ["homepage"],
            "sources": [
                {
                    "source_id": "homepage",
                    "kind": "url",
                    "purpose": "homepage",
                    "ref": "https://example.com",
                }
            ],
        },
        "domains_supported": domains_supported,
        "domain_primary": domain_primary,
        "audience": {
            "primary_audience": "general_consumers",
            "audience_sophistication": "medium",
            "audience_context": "",
        },
        "content_strategy": {
            "allowed_intents": ["thought_leadership"],
            "allowed_product_recommendation_forms": [],
            "allowed_thought_leadership_forms": ["core_insight_essay"],
            "default_content_depth": "short",
        },
        "topic_policy": {
            "allowlist": [
                "Replace this with a real topic 1",
                "Replace this with a real topic 2",
            ]
        },
        "persona_by_domain": {
            d: {
                "primary_persona": "practical_expert",
                "persona_modifiers": ["none"],
                "science_explicitness": "implied",
                "personal_presence": "none",
                "narration_mode": "third_person_only",
            }
            for d in domains_supported
        },
        "commercial_policy": {
            "commercial_posture": "invisible",
            "cta_policy": "none",
            "prohibited_behaviors": ["fake_scarcity", "hype_superlatives", "pressure_language"],
        },
        "disclaimer_policy": {
            "required": True,
            "disclaimer_text": "Replace with the client’s required disclosure/disclaimer.",
            "locations": ["footer"],
        },
        "delivery_policy": {
            "delivery_channels": ["blog_article"],
            "delivery_destinations": ["client_website"],
            "delivery_strategy": "single_canonical_article",
            "auto_publish": False,
        },
        "cadence": {
            "publication_cadence": "on_demand",
            "preferred_publish_days": [],
            "time_zone": "UTC",
        },
    }


def scaffold_request_dict(
    *,
    brand_id: str,
    publish_date: date,
    domain: str,
) -> dict:
    brand_id = _ensure_nonempty(brand_id, "brand_id")
    domain = _ensure_nonempty(domain, "domain")

    return {
        "brand_id": brand_id,
        "publish": {"publish_date": publish_date.isoformat()},
        "intent": "thought_leadership",
        "form": "core_insight_essay",
        "domain": domain,
        "topic": {"mode": "auto"},
        "delivery_target": {"destination": "client_website", "channel": "blog_article"},
        "products": {"mode": "none", "items": []},
    }


def write_onboarding_files(
    *,
    repo_root: Path,
    brand_id: str,
    domains_supported: list[str],
    domain_primary: str,
    publish_date: date,
) -> OnboardPaths:
    brands_dir = repo_root / "content_factory" / "brands"
    requests_dir = repo_root / "content_factory" / "requests"
    brands_dir.mkdir(parents=True, exist_ok=True)
    requests_dir.mkdir(parents=True, exist_ok=True)

    brand_path = brands_dir / f"{brand_id}.yaml"
    request_path = requests_dir / f"{brand_id}_{publish_date.isoformat()}.yaml"

    brand_dict = scaffold_brand_profile_dict(
        brand_id=brand_id,
        domains_supported=domains_supported,
        domain_primary=domain_primary,
    )
    request_dict = scaffold_request_dict(
        brand_id=brand_id,
        publish_date=publish_date,
        domain=domain_primary,
    )

    brand_path.write_text(yaml.safe_dump(brand_dict, sort_keys=False), encoding="utf-8")
    request_path.write_text(yaml.safe_dump(request_dict, sort_keys=False), encoding="utf-8")

    return OnboardPaths(brand_path=brand_path, request_path=request_path)
