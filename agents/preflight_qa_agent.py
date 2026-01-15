from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

from schemas.preflight import PreflightQAReport


_PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}")  # catches {{INTRO}}, {{PICK:...}} etc.

# Common "we tested" style claims we must avoid
_FORBIDDEN_TESTING_PHRASES = [
    "we tested",
    "we've tested",
    "we have tested",
    "our testing",
    "hands-on testing",
    "we tried",
    "we've tried",
    "we have tried",
    "we reviewed",
    "our review found",
    "in our tests",
    "we put it through",
]

# Missing-space-after-punctuation patterns like "files.Skip"
# We keep this conservative: only flag lower->punct->Upper (common typo) to avoid false positives like "U.S."
_MISSING_SPACE_AFTER_PUNCT_RE = re.compile(r"(?<=[a-z])[.!?](?=[A-Z])")

# Weak but useful: detect any leftover HTML-ish <hr /> formatting issues is okay, not an error.
# We'll ignore <hr /> itself.


def _count_placeholders(text: str) -> int:
    return len(_PLACEHOLDER_RE.findall(text or ""))


def _find_placeholders(text: str, limit: int = 10) -> list[str]:
    found = _PLACEHOLDER_RE.findall(text or "")
    return found[:limit]


def _contains_forbidden_testing(text: str) -> list[str]:
    t = (text or "").lower()
    hits = []
    for p in _FORBIDDEN_TESTING_PHRASES:
        if p in t:
            hits.append(p)
    return hits


def _missing_space_after_punct_samples(text: str, limit: int = 10) -> list[str]:
    out: list[str] = []
    for m in _MISSING_SPACE_AFTER_PUNCT_RE.finditer(text or ""):
        start = max(0, m.start() - 18)
        end = min(len(text), m.end() + 18)
        out.append(text[start:end].replace("\n", " "))
        if len(out) >= limit:
            break
    return out


def _parse_frontmatter_value(frontmatter: dict, key: str) -> str:
    v = frontmatter.get(key)
    if v is None:
        return ""
    if isinstance(v, (str, int, float)):
        return str(v).strip()
    return ""


def _is_iso_datetime(s: str) -> bool:
    # Accept "Z" and offset variants
    s = (s or "").strip()
    if not s:
        return False
    try:
        if s.endswith("Z"):
            datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            datetime.fromisoformat(s)
        return True
    except Exception:
        return False


class PreflightQAAgent:
    """
    Deterministic QA checks to prevent publishing obviously-bad posts.

    This agent does NOT mutate content.
    It returns a report with errors/warnings and an ok flag.
    """

    def __init__(self, *, strict: bool = True) -> None:
        self._strict = strict

    def run(
        self,
        *,
        final_markdown: str,
        frontmatter: dict,
        intro_text: str,
        picks_texts: list[str],
        products: list[dict],
    ) -> PreflightQAReport:
        errors: list[str] = []
        warnings: list[str] = []
        metrics: dict[str, int] = {}

        # 1) Frontmatter presence & sanity
        title = _parse_frontmatter_value(frontmatter, "title")
        desc = _parse_frontmatter_value(frontmatter, "description")
        published_at = _parse_frontmatter_value(frontmatter, "publishedAt")
        hero_image = _parse_frontmatter_value(frontmatter, "heroImage")
        hero_alt = _parse_frontmatter_value(frontmatter, "heroAlt")

        if not title:
            errors.append("Frontmatter missing title.")
        if not desc:
            errors.append("Frontmatter missing description.")
        if not published_at:
            errors.append("Frontmatter missing publishedAt.")
        elif not _is_iso_datetime(published_at):
            warnings.append(f"publishedAt is not a valid ISO datetime: {published_at!r}")

        if not hero_image:
            errors.append("Frontmatter missing heroImage.")
        if not hero_alt:
            errors.append("Frontmatter missing heroAlt.")

        # 2) Placeholders must be fully resolved
        placeholders_count = _count_placeholders(final_markdown)
        metrics["placeholders_count"] = placeholders_count
        if placeholders_count > 0:
            ph = _find_placeholders(final_markdown, limit=12)
            errors.append(f"Unresolved placeholders detected ({placeholders_count}). Examples: {ph}")

        # 3) Intro must exist and not be placeholder-ish
        if not (intro_text or "").strip():
            errors.append("Intro section appears empty.")

        # 4) Picks must exist
        metrics["products_count"] = len(products or [])
        metrics["picks_count"] = len(picks_texts or [])
        if len(products or []) < 5:
            warnings.append(f"Low product count ({len(products or [])}). Consider >= 5.")
        if len(picks_texts or []) == 0:
            errors.append("No pick writeups extracted under '## The picks'.")

        # 5) Ensure each pick includes a "Skip it if" clause (credibility pattern)
        missing_skip = []
        for i, p in enumerate(picks_texts or []):
            if "skip it" not in (p or "").lower():
                missing_skip.append(i + 1)
        if missing_skip:
            errors.append(f"Missing 'Skip it if…' guidance for pick(s): {missing_skip}")

        # 6) Forbidden claims: testing/review language
        hits = _contains_forbidden_testing(final_markdown)
        metrics["forbidden_testing_hits"] = len(hits)
        if hits:
            errors.append(f"Forbidden testing/review claims detected: {sorted(set(hits))}")

        # 7) Formatting nits: missing spaces after punctuation like 'files.Skip'
        samples = _missing_space_after_punct_samples(final_markdown, limit=8)
        metrics["missing_space_after_punct_hits"] = len(samples)
        if samples:
            warnings.append(
                "Possible missing space after punctuation (examples): "
                + " | ".join(samples)
            )

        # Outcome
        ok = len(errors) == 0
        mode = "block" if self._strict else "warn_only"

        # If not strict, downgrade errors to warnings and allow publishing
        if not self._strict and errors:
            warnings.extend([f"(non-blocking) {e}" for e in errors])
            errors = []
            ok = True

        return PreflightQAReport(
            ok=ok,
            strict=self._strict,
            errors=errors,
            warnings=warnings,
            metrics=metrics,
            mode=mode,
        )
