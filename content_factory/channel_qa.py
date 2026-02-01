from __future__ import annotations

from content_factory.adapters.common import extract_topic_from_artifact
from content_factory.artifact_models import BlockType, ContentArtifact
from content_factory.models import (
    BrandProfile,
    ContentRequest,
    DeliveryChannel,
    DeliveryDestination,
    DisclaimerLocation,
)


def _has_nonempty_non_topic_paragraph(artifact: ContentArtifact) -> bool:
    for sec in artifact.sections:
        for b in sec.blocks:
            if b.type != BlockType.paragraph:
                continue
            txt = (b.text or "").strip()
            if not txt:
                continue
            if txt.lower().startswith("topic:"):
                continue
            return True
    return False


def _email_subject_and_preheader(*, brand: BrandProfile, request: ContentRequest, artifact: ContentArtifact) -> tuple[str, str]:
    topic = extract_topic_from_artifact(artifact)
    subject = topic or f"{brand.brand_id}: {request.intent.value}"

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

    return subject.strip(), preheader.strip()


def validate_artifact_against_channel_specs(*, brand: BrandProfile, request: ContentRequest, artifact: ContentArtifact) -> None:
    """Channel-appropriate QA checks.

    These checks are intentionally about deliverability/shape, not "content correctness".
    They should hard-fail so the pipeline never silently emits broken outputs.
    """

    errors: list[str] = []

    topic = extract_topic_from_artifact(artifact)
    if not topic.strip():
        errors.append("artifact must include a Topic: paragraph for downstream delivery")

    if not artifact.claims:
        errors.append("artifact.claims must be non-empty after generation")

    if not _has_nonempty_non_topic_paragraph(artifact):
        errors.append("artifact must include at least one non-topic paragraph after generation")

    # Disclaimer placement is part of channel QA because it affects rendered outputs.
    if brand.disclaimer_policy.required and DisclaimerLocation.footer in brand.disclaimer_policy.locations:
        disclaimer = (brand.disclaimer_policy.disclaimer_text or "").strip()
        if disclaimer:
            last_section = artifact.sections[-1] if artifact.sections else None
            if not last_section or not last_section.blocks:
                errors.append("footer disclaimer required but artifact has no sections/blocks")
            else:
                last_block = last_section.blocks[-1]
                if not (
                    last_block.type == BlockType.callout
                    and (last_block.text or "").strip() == disclaimer
                ):
                    errors.append("footer disclaimer must be the last block in the last section")

    if request.delivery_target.channel == DeliveryChannel.email:
        # Delivery target constraints are still enforced by adapter, but QA gives a clearer failure earlier.
        if request.delivery_target.destination != DeliveryDestination.email_list:
            errors.append(
                "email channel requires delivery_target.destination=email_list"
            )

        subject, preheader = _email_subject_and_preheader(brand=brand, request=request, artifact=artifact)
        if not subject:
            errors.append("email subject must not be empty")
        if not preheader:
            errors.append("email preheader must not be empty")
        if len(preheader) > 140:
            errors.append("email preheader must be <= 140 characters")

    if request.delivery_target.channel == DeliveryChannel.social_longform:
        # Only enforce sizing for the LinkedIn destination we support today.
        if request.delivery_target.destination == DeliveryDestination.linkedin:
            parts: list[str] = []
            if topic:
                parts.append(topic)
            for sec in artifact.sections:
                # Plain-text approximation: headings + blocks.
                if sec.heading and sec.heading.strip():
                    parts.append(sec.heading.strip())
                for b in sec.blocks:
                    if b.type in (BlockType.paragraph, BlockType.callout, BlockType.quote) and b.text:
                        t = b.text.strip()
                        if t:
                            parts.append(t)
                    elif b.type in (BlockType.bullets, BlockType.numbered) and b.items:
                        for it in b.items:
                            it2 = (it or "").strip()
                            if it2:
                                parts.append(it2)
            rendered = "\n\n".join([p for p in parts if p.strip()]).strip()
            if len(rendered) > 3000:
                errors.append("LinkedIn social_longform output must be <= 3000 characters")

    if errors:
        msg = "\n".join(f"- {e}" for e in errors)
        raise ValueError(f"Channel QA failed:\n{msg}")
