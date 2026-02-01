from __future__ import annotations

import unittest

from content_factory.brand_context import _extract_text_fields_from_html, _merge_signals


class TestBrandContextExtraction(unittest.TestCase):
    def test_extracts_title_heading_description(self) -> None:
        html = """
        <html>
          <head>
            <title>Example Brand</title>
            <meta name='description' content='We help leaders communicate.'>
          </head>
          <body>
            <h1>Clarity under pressure</h1>
            <h2>Practical guidance</h2>
          </body>
        </html>
        """
        s = _extract_text_fields_from_html(html)
        self.assertIn("Example Brand", s.titles)
        self.assertIn("Clarity under pressure", s.headings)
        self.assertIn("We help leaders communicate.", s.descriptions)

    def test_merge_dedupes(self) -> None:
        a = _extract_text_fields_from_html("<title>A</title><h1>H</h1>")
        b = _extract_text_fields_from_html("<title>A</title><h1>H</h1><h2>H2</h2>")
        m = _merge_signals([a, b])
        self.assertEqual(m.titles.count("A"), 1)
        self.assertEqual(m.headings.count("H"), 1)
        self.assertIn("H2", m.headings)
