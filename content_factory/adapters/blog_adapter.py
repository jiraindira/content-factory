from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from content_factory.adapters.common import (
    RenderedDelivery,
    ensure_delivery_target_matches,
    extract_topic_from_artifact,
    section_to_plain_text,
)
from content_factory.artifact_models import ContentArtifact
from content_factory.models import BrandProfile, ContentRequest, DeliveryChannel, DeliveryDestination


def _published_at_iso(*, request: ContentRequest) -> str:
    d = request.publish.publish_date
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def render_astro_markdown(*, brand: BrandProfile, request: ContentRequest, artifact: ContentArtifact) -> str:
    # Allow hosted_by_us or client_website, but still channel must be blog_article.
    if request.delivery_target.channel != DeliveryChannel.blog_article:
        raise ValueError(
            f"Blog adapter channel mismatch: expected={DeliveryChannel.blog_article.value} got={request.delivery_target.channel.value}"
        )
    if request.delivery_target.destination not in (DeliveryDestination.hosted_by_us, DeliveryDestination.client_website):
        raise ValueError(
            "Blog adapter destination mismatch: expected hosted_by_us or client_website "
            f"got={request.delivery_target.destination.value}"
        )

    topic = extract_topic_from_artifact(artifact)
    title = topic or f"{request.intent.value}: {request.form.value}"
    description = f"{request.domain.value} — {request.intent.value}"

    frontmatter = {
        "title": title,
        "description": description,
        "publishedAt": _published_at_iso(request=request),
        "categories": [request.domain.value],
        "audience": getattr(brand.audience.primary_audience, "value", str(brand.audience.primary_audience)),
        "products": [
            {
                "pick_id": p.pick_id,
                "catalog_key": None,
                "title": p.title,
                "url": p.url,
                "rating": p.rating,
                "reviews_count": p.reviews_count,
                "description": "",
            }
            for p in (artifact.products or [])
        ],
    }

    fm = yaml.safe_dump(frontmatter, sort_keys=False).strip()

    body_parts: list[str] = []
    for sec in artifact.sections:
        heading = sec.heading or sec.id.replace("_", " ").title()
        body_parts.append(f"## {heading}")
        t = section_to_plain_text(sec)
        if t:
            # section_to_plain_text includes heading again; we want just body blocks.
            # so render blocks only.
            body_parts.append("\n" + "\n".join(line for line in t.splitlines()[1:]).strip())

    body = "\n\n".join([p for p in body_parts if p.strip()]).strip() + "\n"

    return f"---\n{fm}\n---\n\n{body}"


def render_blog_delivery(*, brand: BrandProfile, request: ContentRequest, artifact: ContentArtifact) -> RenderedDelivery:
    filename = f"{artifact.run_id}.md"
    return RenderedDelivery(filename=filename, mime_type="text/markdown", content=render_astro_markdown(brand=brand, request=request, artifact=artifact))


def write_blog_delivery(*, repo_root: Path, delivery: RenderedDelivery) -> Path:
    out_dir = repo_root / "content_factory" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / delivery.filename
    out_path.write_text(delivery.content, encoding="utf-8")
    return out_path
