from __future__ import annotations

from pathlib import Path

from content_factory.adapters.common import (
    RenderedDelivery,
    ensure_delivery_target_matches,
    extract_topic_from_artifact,
    section_to_plain_text,
)
from content_factory.artifact_models import ContentArtifact
from content_factory.models import BrandProfile, ContentRequest, DeliveryChannel, DeliveryDestination


def render_linkedin_text(*, brand: BrandProfile, request: ContentRequest, artifact: ContentArtifact) -> str:
    ensure_delivery_target_matches(
        target_channel=DeliveryChannel.social_longform,
        target_destination=DeliveryDestination.linkedin,
        actual_channel=request.delivery_target.channel,
        actual_destination=request.delivery_target.destination,
    )

    topic = extract_topic_from_artifact(artifact)
    parts: list[str] = []

    if topic:
        parts.append(topic)

    for sec in artifact.sections:
        t = section_to_plain_text(sec)
        if t:
            parts.append(t)

    # LinkedIn: simple, readable spacing.
    return "\n\n".join(parts).strip() + "\n"


def render_linkedin_delivery(*, brand: BrandProfile, request: ContentRequest, artifact: ContentArtifact) -> RenderedDelivery:
    filename = f"{artifact.run_id}.linkedin.txt"
    return RenderedDelivery(filename=filename, mime_type="text/plain", content=render_linkedin_text(brand=brand, request=request, artifact=artifact))


def write_linkedin_delivery(*, repo_root: Path, delivery: RenderedDelivery) -> Path:
    out_dir = repo_root / "content_factory" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / delivery.filename
    out_path.write_text(delivery.content, encoding="utf-8")
    return out_path
