from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from content_factory.artifact_models import Block, BlockType, ContentArtifact, Section
from content_factory.models import DeliveryChannel, DeliveryDestination


@dataclass(frozen=True)
class RenderedDelivery:
    filename: str
    mime_type: str
    content: str


def ensure_delivery_target_matches(
    *,
    target_channel: DeliveryChannel,
    target_destination: DeliveryDestination,
    actual_channel: DeliveryChannel,
    actual_destination: DeliveryDestination,
) -> None:
    if actual_channel != target_channel:
        raise ValueError(
            f"Adapter channel mismatch: expected={target_channel.value} got={actual_channel.value}"
        )
    if actual_destination != target_destination:
        raise ValueError(
            f"Adapter destination mismatch: expected={target_destination.value} got={actual_destination.value}"
        )


def extract_topic_from_artifact(artifact: ContentArtifact) -> str:
    # Deterministic contract (v1 compiler): the topic is emitted as a paragraph "Topic: <value>".
    for sec in artifact.sections:
        for block in sec.blocks:
            if block.type == BlockType.paragraph and block.text:
                t = block.text.strip()
                if t.lower().startswith("topic:"):
                    return t.split(":", 1)[1].strip() or t
    return ""


def blocks_to_plain_text(blocks: Iterable[Block]) -> str:
    out: list[str] = []
    for b in blocks:
        if b.type in (BlockType.paragraph, BlockType.callout, BlockType.quote):
            if b.text and b.text.strip():
                out.append(b.text.strip())
        elif b.type in (BlockType.bullets, BlockType.numbered):
            items = b.items or []
            for i, it in enumerate(items, start=1):
                it2 = (it or "").strip()
                if not it2:
                    continue
                prefix = "- " if b.type == BlockType.bullets else f"{i}. "
                out.append(prefix + it2)
        elif b.type == BlockType.divider:
            out.append("---")
    return "\n".join(out).strip()


def section_to_plain_text(section: Section) -> str:
    parts: list[str] = []
    if section.heading:
        parts.append(section.heading.strip())
    body = blocks_to_plain_text(section.blocks)
    if body:
        parts.append(body)
    return "\n\n".join(parts).strip()
