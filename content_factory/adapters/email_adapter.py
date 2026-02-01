from __future__ import annotations

import json
from html import escape
from pathlib import Path

from content_factory.adapters.common import (
    RenderedDelivery,
    blocks_to_plain_text,
    ensure_delivery_target_matches,
    extract_topic_from_artifact,
)
from content_factory.artifact_models import BlockType, ContentArtifact
from content_factory.models import BrandProfile, ContentRequest, DeliveryChannel, DeliveryDestination


def render_email_payload(*, brand: BrandProfile, request: ContentRequest, artifact: ContentArtifact) -> dict:
    ensure_delivery_target_matches(
        target_channel=DeliveryChannel.email,
        target_destination=DeliveryDestination.email_list,
        actual_channel=request.delivery_target.channel,
        actual_destination=request.delivery_target.destination,
    )

    topic = extract_topic_from_artifact(artifact)
    subject = topic or f"{brand.brand_id}: {request.intent.value}"

    # Preheader: first non-empty paragraph that isn't the topic line.
    preheader = ""
    for sec in artifact.sections:
        for b in sec.blocks:
            if b.type == BlockType.paragraph and b.text and b.text.strip():
                txt = b.text.strip()
                if txt.lower().startswith("topic:"):
                    continue
                preheader = txt[:140]
                break
        if preheader:
            break

    # Plain text
    text_parts: list[str] = []
    for sec in artifact.sections:
        t = blocks_to_plain_text(sec.blocks)
        if t:
            if sec.heading:
                text_parts.append(sec.heading)
            text_parts.append(t)
    body_text = "\n\n".join(text_parts).strip()

    # Basic HTML
    html_parts: list[str] = []
    html_parts.append('<div style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; line-height: 1.5;">')
    for sec in artifact.sections:
        if sec.heading:
            html_parts.append(f"<h2>{escape(sec.heading)}</h2>")
        for b in sec.blocks:
            if b.type == BlockType.paragraph and b.text and b.text.strip():
                html_parts.append(f"<p>{escape(b.text.strip())}</p>")
            elif b.type == BlockType.callout and b.text and b.text.strip():
                html_parts.append(
                    '<div style="border-left: 4px solid #ddd; padding: 8px 12px; margin: 12px 0; color: #333;">'
                    + escape(b.text.strip())
                    + "</div>"
                )
            elif b.type == BlockType.quote and b.text and b.text.strip():
                html_parts.append(f"<blockquote>{escape(b.text.strip())}</blockquote>")
            elif b.type == BlockType.bullets and b.items:
                html_parts.append("<ul>")
                for it in b.items:
                    it2 = (it or "").strip()
                    if it2:
                        html_parts.append(f"<li>{escape(it2)}</li>")
                html_parts.append("</ul>")
            elif b.type == BlockType.numbered and b.items:
                html_parts.append("<ol>")
                for it in b.items:
                    it2 = (it or "").strip()
                    if it2:
                        html_parts.append(f"<li>{escape(it2)}</li>")
                html_parts.append("</ol>")
            elif b.type == BlockType.divider:
                html_parts.append("<hr />")
    html_parts.append("</div>")

    body_html = "\n".join(html_parts).strip()

    return {
        "subject": subject,
        "preheader": preheader,
        "body_text": body_text,
        "body_html": body_html,
        "meta": {
            "brand_id": artifact.brand_id,
            "run_id": artifact.run_id,
            "intent": artifact.intent,
            "form": artifact.form,
            "domain": artifact.domain,
        },
    }


def render_email_delivery(*, brand: BrandProfile, request: ContentRequest, artifact: ContentArtifact) -> RenderedDelivery:
    payload = render_email_payload(brand=brand, request=request, artifact=artifact)
    filename = f"{artifact.run_id}.email.json"
    return RenderedDelivery(filename=filename, mime_type="application/json", content=json.dumps(payload, indent=2))


def write_email_delivery(*, repo_root: Path, delivery: RenderedDelivery) -> Path:
    out_dir = repo_root / "content_factory" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / delivery.filename
    out_path.write_text(delivery.content, encoding="utf-8")
    return out_path
