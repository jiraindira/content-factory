from __future__ import annotations

from pathlib import Path

from content_factory.adapters.blog_adapter import render_blog_delivery, write_blog_delivery
from content_factory.adapters.common import RenderedDelivery
from content_factory.adapters.email_adapter import render_email_delivery, write_email_delivery
from content_factory.adapters.linkedin_adapter import render_linkedin_delivery, write_linkedin_delivery
from content_factory.artifact_models import ContentArtifact
from content_factory.models import BrandProfile, ContentRequest, DeliveryChannel


def render_for_request(*, brand: BrandProfile, request: ContentRequest, artifact: ContentArtifact) -> RenderedDelivery:
    ch = request.delivery_target.channel
    if ch == DeliveryChannel.blog_article:
        return render_blog_delivery(brand=brand, request=request, artifact=artifact)
    if ch == DeliveryChannel.email:
        return render_email_delivery(brand=brand, request=request, artifact=artifact)
    if ch == DeliveryChannel.social_longform:
        return render_linkedin_delivery(brand=brand, request=request, artifact=artifact)

    raise ValueError(f"No adapter implemented for delivery_target.channel={ch.value}")


def write_delivery(*, repo_root: Path, delivery: RenderedDelivery) -> Path:
    if delivery.filename.endswith(".md"):
        return write_blog_delivery(repo_root=repo_root, delivery=delivery)
    if delivery.filename.endswith(".email.json"):
        return write_email_delivery(repo_root=repo_root, delivery=delivery)
    if delivery.filename.endswith(".linkedin.txt"):
        return write_linkedin_delivery(repo_root=repo_root, delivery=delivery)

    out_dir = repo_root / "content_factory" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / delivery.filename
    out_path.write_text(delivery.content, encoding="utf-8")
    return out_path
