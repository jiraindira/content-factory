from __future__ import annotations

import unittest
from unittest.mock import patch

from content_factory.brand_context import FETCH_USER_AGENT, _robots_allows


class TestRobotsCompliance(unittest.TestCase):
    def test_robots_disallow_hard_fails(self) -> None:
        robots_txt = b"User-agent: AIContentFactoryFetcher-1.0\nDisallow: /private/\n"

        def fake_get(url: str, *, user_agent: str, timeout_seconds: float = 20.0):
            class R:
                status = 200
                data = robots_txt

            return R()

        with patch("content_factory.brand_context._http_get_bytes", new=fake_get):
            allowed = _robots_allows("https://example.com/private/page", user_agent=FETCH_USER_AGENT)
            self.assertFalse(allowed)

    def test_robots_404_allows(self) -> None:
        def fake_get(url: str, *, user_agent: str, timeout_seconds: float = 20.0):
            class R:
                status = 404
                data = b""

            return R()

        with patch("content_factory.brand_context._http_get_bytes", new=fake_get):
            allowed = _robots_allows("https://example.com/anything", user_agent=FETCH_USER_AGENT)
            self.assertTrue(allowed)
