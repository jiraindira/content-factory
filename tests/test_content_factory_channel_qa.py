from __future__ import annotations

import unittest
from pathlib import Path

from content_factory.brand_context import BrandContextArtifact
from content_factory.channel_qa import validate_artifact_against_channel_specs
from content_factory.compiler import compile_content_artifact
from content_factory.generation import generate_filled_artifact
from content_factory.models import DeliveryChannel, DeliveryDestination
from content_factory.validation import load_brand_profile, load_content_request, validate_request_against_brand


def _ctx(brand_id: str) -> BrandContextArtifact:
    return BrandContextArtifact(
        brand_id=brand_id,
        generated_at="2026-02-01T00:00:00Z",
        fetch_user_agent="AIContentFactoryFetcher-1.0",
        sources=[],
        signals={"titles": [], "headings": [], "descriptions": [], "positioning_snippets": [], "key_terms": []},
    )


class TestChannelQA(unittest.TestCase):
    def test_passes_for_linkedin_thought_leadership(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        brand = load_brand_profile(repo / "content_factory" / "brands" / "alisa_amouage.yaml")
        req = load_content_request(repo / "content_factory" / "requests" / "alisa_2026-02-01.yaml")

        req.delivery_target.channel = DeliveryChannel.social_longform
        req.delivery_target.destination = DeliveryDestination.linkedin

        validate_request_against_brand(brand=brand, request=req)
        artifact = compile_content_artifact(brand=brand, request=req, brand_context=_ctx(brand.brand_id), run_id="run")
        _ = generate_filled_artifact(brand=brand, request=req, artifact=artifact)

        validate_artifact_against_channel_specs(brand=brand, request=req, artifact=artifact)

    def test_passes_for_email_product_recommendation(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        brand = load_brand_profile(repo / "content_factory" / "brands" / "everyday_buying_guide.yaml")
        req = load_content_request(repo / "content_factory" / "requests" / "everyday_buying_guide_2026-02-01.yaml")

        req.delivery_target.channel = DeliveryChannel.email
        req.delivery_target.destination = DeliveryDestination.email_list

        validate_request_against_brand(brand=brand, request=req)
        artifact = compile_content_artifact(brand=brand, request=req, brand_context=_ctx(brand.brand_id), run_id="run")
        _ = generate_filled_artifact(brand=brand, request=req, artifact=artifact)

        validate_artifact_against_channel_specs(brand=brand, request=req, artifact=artifact)

    def test_email_preheader_required(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        brand = load_brand_profile(repo / "content_factory" / "brands" / "everyday_buying_guide.yaml")
        req = load_content_request(repo / "content_factory" / "requests" / "everyday_buying_guide_2026-02-01.yaml")

        req.delivery_target.channel = DeliveryChannel.email
        req.delivery_target.destination = DeliveryDestination.email_list

        validate_request_against_brand(brand=brand, request=req)
        artifact = compile_content_artifact(brand=brand, request=req, brand_context=_ctx(brand.brand_id), run_id="run")
        _ = generate_filled_artifact(brand=brand, request=req, artifact=artifact)

        # Remove all non-topic paragraphs to force missing preheader.
        for sec in artifact.sections:
            sec.blocks = [
                b
                for b in sec.blocks
                if not (
                    b.type.value == "paragraph"
                    and (b.text or "").strip()
                    and not (b.text or "").strip().lower().startswith("topic:")
                )
            ]

        with self.assertRaises(ValueError) as ctx:
            validate_artifact_against_channel_specs(brand=brand, request=req, artifact=artifact)
        self.assertIn("email preheader must not be empty", str(ctx.exception))
