from __future__ import annotations

import json
import unittest
from pathlib import Path

from content_factory.adapters.blog_adapter import render_astro_markdown
from content_factory.adapters.email_adapter import render_email_payload
from content_factory.adapters.linkedin_adapter import render_linkedin_text
from content_factory.brand_context import BrandContextArtifact
from content_factory.compiler import compile_content_artifact
from content_factory.models import DeliveryChannel, DeliveryDestination
from content_factory.validation import load_brand_profile, load_content_request, validate_request_against_brand


class TestDeliveryAdapters(unittest.TestCase):
    def _ctx(self, brand_id: str) -> BrandContextArtifact:
        return BrandContextArtifact(
            brand_id=brand_id,
            generated_at="2026-02-01T00:00:00Z",
            fetch_user_agent="AIContentFactoryFetcher-1.0",
            sources=[],
            signals={"titles": [], "headings": [], "descriptions": [], "positioning_snippets": [], "key_terms": []},
        )

    def test_email_adapter_exports_json_payload(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        brand = load_brand_profile(repo / "content_factory" / "brands" / "everyday_buying_guide.yaml")
        req = load_content_request(
            repo / "content_factory" / "requests" / "everyday_buying_guide_2026-02-01.yaml"
        )

        # Force delivery target to email/email_list for adapter test.
        req.delivery_target.channel = DeliveryChannel.email
        req.delivery_target.destination = DeliveryDestination.email_list

        validate_request_against_brand(brand=brand, request=req)
        artifact = compile_content_artifact(
            brand=brand, request=req, brand_context=self._ctx(brand.brand_id), run_id="run"
        )

        payload = render_email_payload(brand=brand, request=req, artifact=artifact)
        self.assertIn("subject", payload)
        self.assertIn("body_text", payload)
        self.assertIn("body_html", payload)
        # Must be valid JSON-serializable
        json.dumps(payload)

    def test_linkedin_adapter_renders_text(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        brand = load_brand_profile(repo / "content_factory" / "brands" / "alisa_amouage.yaml")
        req = load_content_request(repo / "content_factory" / "requests" / "alisa_2026-02-01.yaml")

        req.delivery_target.channel = DeliveryChannel.social_longform
        req.delivery_target.destination = DeliveryDestination.linkedin

        validate_request_against_brand(brand=brand, request=req)
        artifact = compile_content_artifact(brand=brand, request=req, brand_context=self._ctx(brand.brand_id), run_id="run")

        text = render_linkedin_text(brand=brand, request=req, artifact=artifact)
        self.assertTrue(text.strip())

    def test_blog_adapter_renders_markdown_with_frontmatter(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        brand = load_brand_profile(repo / "content_factory" / "brands" / "everyday_buying_guide.yaml")
        req = load_content_request(repo / "content_factory" / "requests" / "everyday_buying_guide_2026-02-01.yaml")

        req.delivery_target.channel = DeliveryChannel.blog_article
        req.delivery_target.destination = DeliveryDestination.hosted_by_us

        validate_request_against_brand(brand=brand, request=req)
        artifact = compile_content_artifact(brand=brand, request=req, brand_context=self._ctx(brand.brand_id), run_id="run")

        md = render_astro_markdown(brand=brand, request=req, artifact=artifact)
        self.assertIn("---", md)
        self.assertIn("publishedAt:", md)
        self.assertIn("##", md)

    def test_adapter_rejects_mismatched_target(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        brand = load_brand_profile(repo / "content_factory" / "brands" / "alisa_amouage.yaml")
        req = load_content_request(repo / "content_factory" / "requests" / "alisa_2026-02-01.yaml")

        # leave as original (blog-ish) but try rendering email
        artifact = compile_content_artifact(brand=brand, request=req, brand_context=self._ctx(brand.brand_id), run_id="run")
        with self.assertRaises(ValueError):
            render_email_payload(brand=brand, request=req, artifact=artifact)
