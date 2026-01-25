from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from schemas.preflight import PreflightQAReport, QAIssue


# -----------------------------
# Rule IDs (stable contracts)
# -----------------------------
RULE_MISSING_FRONTMATTER_TITLE = "RULE_MISSING_FRONTMATTER_TITLE"
RULE_MISSING_FRONTMATTER_DESCRIPTION = "RULE_MISSING_FRONTMATTER_DESCRIPTION"
RULE_MISSING_FRONTMATTER_PUBLISHED_AT = "RULE_MISSING_FRONTMATTER_PUBLISHED_AT"
RULE_INVALID_FRONTMATTER_PUBLISHED_AT = "RULE_INVALID_FRONTMATTER_PUBLISHED_AT"
RULE_MISSING_FRONTMATTER_HERO_IMAGE = "RULE_MISSING_FRONTMATTER_HERO_IMAGE"
RULE_MISSING_FRONTMATTER_HERO_ALT = "RULE_MISSING_FRONTMATTER_HERO_ALT"

RULE_UNRESOLVED_PLACEHOLDERS = "RULE_UNRESOLVED_PLACEHOLDERS"
RULE_EMPTY_INTRO = "RULE_EMPTY_INTRO"
RULE_NO_PICKS_EXTRACTED = "RULE_NO_PICKS_EXTRACTED"
RULE_LOW_PRODUCT_COUNT = "RULE_LOW_PRODUCT_COUNT"
RULE_MISSING_SKIP_IT_IF = "RULE_MISSING_SKIP_IT_IF"
RULE_FORBIDDEN_TESTING_CLAIMS = "RULE_FORBIDDEN_TESTING_CLAIMS"
RULE_MISSING_SPACE_AFTER_PUNCT = "RULE_MISSING_SPACE_AFTER_PUNCT"

# NEW: UI-contract rules (buttons + quick links depend on these)
RULE_PICK_MARKER_HEADING_CONTRACT = "RULE_PICK_MARKER_HEADING_CONTRACT"
RULE_PICK_ID_ALIGNMENT = "RULE_PICK_ID_ALIGNMENT"
RULE_PICK_TITLE_ALIGNMENT = "RULE_PICK_TITLE_ALIGNMENT"


_PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}")  # catches {{INTRO}}, {{PICK:...}} etc.

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

_MISSING_SPACE_AFTER_PUNCT_RE = re.compile(r"(?<=[a-z])[.!?](?=[A-Z])")

_SKIP_GUIDANCE_PATTERNS = [
    r"\bskip it\b",
    r"\bskip this\b",
    r"\bskip\b.*\bif\b",
    r"\bpass\b.*\bif\b",
    r"\bnot for you\b.*\bif\b",
    r"\bonly worth it\b.*\bif\b",
    r"\boverkill\b.*\bif\b",
    r"\byou can skip\b",
]

# Picks section parsing
_PICK_ID_COMMENT_RE = re.compile(r"^\s*<!--\s*pick_id:\s*([a-z0-9\-_:]+)\s*-->\s*$", re.I)
_H3_RE = re.compile(r"^\s*###\s+(.+?)\s*$")
_H2_RE = re.compile(r"^\s*##\s+(.+?)\s*$")


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


def _parse_frontmatter_value(frontmatter: dict[str, Any], key: str) -> str:
    v = frontmatter.get(key)
    if v is None:
        return ""
    if isinstance(v, (str, int, float)):
        return str(v).strip()
    return ""


def _is_iso_datetime(s: str) -> bool:
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


def _has_skip_guidance(text: str) -> bool:
    t = (text or "").lower()
    return any(re.search(pat, t) for pat in _SKIP_GUIDANCE_PATTERNS)


def _extract_pick_blocks_from_markdown(final_markdown: str) -> list[dict[str, str]]:
    """
    Deterministically parse picks contract from markdown:

      <!-- pick_id: X -->
      ### Title

    Returns list of {"pick_id":..., "title":...} in the order they appear
    inside the '## The picks' section.
    """
    lines = (final_markdown or "").splitlines()

    # Find "## The picks"
    start = None
    for i, ln in enumerate(lines):
        m = _H2_RE.match(ln)
        if m and m.group(1).strip().lower() == "the picks":
            start = i + 1
            break
    if start is None:
        return []

    # End at next H2
    end = len(lines)
    for j in range(start, len(lines)):
        if j == start:
            continue
        if _H2_RE.match(lines[j]):
            end = j
            break

    picks_lines = lines[start:end]

    out: list[dict[str, str]] = []
    i = 0
    while i < len(picks_lines):
        m = _PICK_ID_COMMENT_RE.match(picks_lines[i])
        if not m:
            i += 1
            continue

        pick_id = m.group(1).strip()
        # next non-empty line must be H3
        k = i + 1
        while k < len(picks_lines) and picks_lines[k].strip() == "":
            k += 1
        if k >= len(picks_lines):
            out.append({"pick_id": pick_id, "title": ""})
            break

        h3 = _H3_RE.match(picks_lines[k])
        if not h3:
            out.append({"pick_id": pick_id, "title": ""})
            i = k + 1
            continue

        title = h3.group(1).strip()
        out.append({"pick_id": pick_id, "title": title})
        i = k + 1

    return out


class PreflightQAAgent:
    """
    Deterministic QA checks to prevent publishing obviously-bad posts.
    Produces rule IDs so a repair agent can fix targeted issues.
    """

    def __init__(self, *, strict: bool = True) -> None:
        self._strict = strict

    def run(
        self,
        *,
        final_markdown: str,
        frontmatter: dict[str, Any],
        intro_text: str,
        picks_texts: list[str],
        products: list[dict],
    ) -> PreflightQAReport:
        issues: list[QAIssue] = []
        metrics: dict[str, int] = {}

        def add(rule_id: str, level: str, message: str, meta: dict[str, Any] | None = None) -> None:
            issues.append(QAIssue(rule_id=rule_id, level=level, message=message, meta=meta or {}))

        # 1) Frontmatter presence & sanity
        title = _parse_frontmatter_value(frontmatter, "title")
        desc = _parse_frontmatter_value(frontmatter, "description")
        published_at = _parse_frontmatter_value(frontmatter, "publishedAt")
        hero_image = _parse_frontmatter_value(frontmatter, "heroImage")
        hero_alt = _parse_frontmatter_value(frontmatter, "heroAlt")

        if not title:
            add(RULE_MISSING_FRONTMATTER_TITLE, "error", "Frontmatter missing title.")
        if not desc:
            add(RULE_MISSING_FRONTMATTER_DESCRIPTION, "error", "Frontmatter missing description.")
        if not published_at:
            add(RULE_MISSING_FRONTMATTER_PUBLISHED_AT, "error", "Frontmatter missing publishedAt.")
        elif not _is_iso_datetime(published_at):
            add(
                RULE_INVALID_FRONTMATTER_PUBLISHED_AT,
                "warning",
                f"publishedAt is not a valid ISO datetime: {published_at!r}",
                {"publishedAt": published_at},
            )

        if not hero_image:
            add(RULE_MISSING_FRONTMATTER_HERO_IMAGE, "error", "Frontmatter missing heroImage.")
        if not hero_alt:
            add(RULE_MISSING_FRONTMATTER_HERO_ALT, "error", "Frontmatter missing heroAlt.")

        # 2) Placeholders must be fully resolved
        placeholders_count = _count_placeholders(final_markdown)
        metrics["placeholders_count"] = placeholders_count
        if placeholders_count > 0:
            ph = _find_placeholders(final_markdown, limit=12)
            add(
                RULE_UNRESOLVED_PLACEHOLDERS,
                "error",
                f"Unresolved placeholders detected ({placeholders_count}).",
                {"examples": ph, "count": placeholders_count},
            )

        # 3) Intro must exist
        if not (intro_text or "").strip():
            add(RULE_EMPTY_INTRO, "error", "Intro section appears empty.")

        # 4) Picks must exist
        metrics["products_count"] = len(products or [])
        metrics["picks_count"] = len(picks_texts or [])
        if len(products or []) < 5:
            add(
                RULE_LOW_PRODUCT_COUNT,
                "warning",
                f"Low product count ({len(products or [])}). Consider >= 5.",
                {"product_count": len(products or [])},
            )
        if len(picks_texts or []) == 0:
            add(RULE_NO_PICKS_EXTRACTED, "error", "No pick writeups extracted under '## The picks'.")

        # 4b) UI contract: pick markers + H3 headings must align with products
        pick_blocks = _extract_pick_blocks_from_markdown(final_markdown)
        metrics["pick_blocks_count"] = len(pick_blocks)

        if pick_blocks:
            # Ensure every marker has a valid heading right after it
            missing_heading = [b["pick_id"] for b in pick_blocks if not (b.get("title") or "").strip()]
            if missing_heading:
                add(
                    RULE_PICK_MARKER_HEADING_CONTRACT,
                    "error",
                    "Pick marker must be followed by an H3 heading: <!-- pick_id: X --> then ### Title.",
                    {"pick_ids_missing_h3": missing_heading},
                )

            # Compare to products list (order matters)
            expected = []
            for p in products or []:
                if isinstance(p, dict):
                    expected.append(
                        {
                            "pick_id": str(p.get("pick_id") or "").strip(),
                            "title": str(p.get("title") or "").strip(),
                        }
                    )

            actual = [{"pick_id": b["pick_id"], "title": b.get("title", "")} for b in pick_blocks]

            exp_ids = [x["pick_id"] for x in expected if x["pick_id"]]
            act_ids = [x["pick_id"] for x in actual if x["pick_id"]]

            if exp_ids and act_ids and exp_ids != act_ids:
                add(
                    RULE_PICK_ID_ALIGNMENT,
                    "error",
                    "Pick IDs in markdown do not match products[].pick_id order. This breaks product cards/buttons.",
                    {"expected_pick_ids": exp_ids, "actual_pick_ids": act_ids},
                )

            # Title alignment (quick links rely on H3 text)
            mismatched_titles: list[dict[str, Any]] = []
            by_id_expected = {x["pick_id"]: x["title"] for x in expected if x["pick_id"]}
            for b in actual:
                pid = b["pick_id"]
                if not pid:
                    continue
                exp_title = (by_id_expected.get(pid) or "").strip()
                act_title = (b.get("title") or "").strip()
                if exp_title and act_title and exp_title != act_title:
                    mismatched_titles.append(
                        {"pick_id": pid, "expected_title": exp_title, "actual_title": act_title}
                    )
            if mismatched_titles:
                add(
                    RULE_PICK_TITLE_ALIGNMENT,
                    "error",
                    "Pick H3 titles must match products[].title exactly (quick links + UI anchors rely on this).",
                    {"mismatches": mismatched_titles},
                )

        # 5) Ensure each pick includes a "skip guidance" clause (intent-based)
        missing_guidance = []
        for i, p in enumerate(picks_texts or []):
            if not _has_skip_guidance(p or ""):
                missing_guidance.append(i + 1)
        if missing_guidance:
            add(
                RULE_MISSING_SKIP_IT_IF,
                "warning",
                "Missing skip-guidance (e.g., 'Skip it if…', 'Pass if…', 'Overkill if…') for one or more picks.",
                {"missing_pick_numbers": missing_guidance},
            )

        # 6) Forbidden claims: testing/review language
        hits = _contains_forbidden_testing(final_markdown)
        metrics["forbidden_testing_hits"] = len(hits)
        if hits:
            add(
                RULE_FORBIDDEN_TESTING_CLAIMS,
                "error",
                "Forbidden testing/review claims detected.",
                {"phrases": sorted(set(hits))},
            )

        # 7) Formatting nits: missing spaces after punctuation
        samples = _missing_space_after_punct_samples(final_markdown, limit=8)
        metrics["missing_space_after_punct_hits"] = len(samples)
        if samples:
            add(
                RULE_MISSING_SPACE_AFTER_PUNCT,
                "warning",
                "Possible missing space after punctuation.",
                {"examples": samples},
            )

        # Outcome logic
        mode = "block" if self._strict else "warn_only"

        errors = [i.message if not i.meta else f"{i.message} {i.meta}" for i in issues if i.level == "error"]
        warnings = [i.message if not i.meta else f"{i.message} {i.meta}" for i in issues if i.level == "warning"]

        ok = len([i for i in issues if i.level == "error"]) == 0

        # If not strict, downgrade errors to warnings and allow publishing
        if not self._strict and not ok:
            for i in issues:
                if i.level == "error":
                    i.level = "warning"  # type: ignore[misc]
            ok = True
            errors = []
            warnings = [i.message if not i.meta else f"{i.message} {i.meta}" for i in issues]

        return PreflightQAReport(
            ok=ok,
            strict=self._strict,
            errors=errors,
            warnings=warnings,
            issues=issues,
            metrics=metrics,
            mode=mode,
        )
