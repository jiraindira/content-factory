from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from content_factory.onboarding import write_onboarding_files
from content_factory.validation import load_brand_profile, load_content_request, validate_request_against_brand


class TestContentFactoryCliOnboarding(unittest.TestCase):
    def test_onboarding_scaffold_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)

            publish_date = date(2026, 2, 1)
            paths = write_onboarding_files(
                repo_root=repo_root,
                brand_id="acme_consulting",
                domains_supported=["leadership"],
                domain_primary="leadership",
                publish_date=publish_date,
            )

            brand = load_brand_profile(paths.brand_path)
            req = load_content_request(paths.request_path)

            # Should validate against itself.
            validate_request_against_brand(brand=brand, request=req)
