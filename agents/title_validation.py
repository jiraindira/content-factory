from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class TitleValidationResult:
    ok: bool
    reasons: list[str]
    inferred_mode: str  # "physical_only" | "digital_only" | "mixed"


_DIGITAL_SIGNAL_TERMS = {
    # General digital/software signals
    "app", "apps", "software", "tool", "tools", "platform", "platforms", "service", "services",
    "online", "web", "cloud", "sync", "automation", "automate", "workflow", "dashboard",
    "template", "templates", "spreadsheet", "spreadsheets",
    "saas", "api", "integration", "integrations", "download", "install", "subscription",
    # Device OS signals
    "ios", "android", "iphone", "ipad", "mobile",
    # Common digital finance/tax verbs
    "efile", "e-file", "efiling", "e-filing",
}

_PHYSICAL_SIGNAL_TERMS = {
    # General physical/hardware signals
    "shredder", "shredders", "folder", "folders", "label", "labels", "scanner", "scanners",
    "printer", "printers", "laminator", "laminators", "box", "boxes", "binder", "binders",
    "filing", "cabinet", "cabinets", "paper", "paperwork", "receipt", "receipts", "documents",
    "envelope", "envelopes", "organizer", "organizers",
    # Generic physical nouns often used in titles
    "gear", "hardware", "device", "devices", "supplies", "equipment",
}

# Title-claim terms that should be supported by corpus evidence.
# These are not topic-specific, they are claim categories.
_CLAIM_TOKENS_REQUIRING_EVIDENCE = {
    # Digital claims
    "app", "apps", "software", "platform", "platforms", "template", "templates", "spreadsheet", "spreadsheets",
    # Physical claims
    "gear", "hardware", "device", "devices", "supplies", "equipment",
}

# If title is "X and Y", X must be supported and Y must be supported.
# We'll handle with generic per-token evidence checks plus mode constraints.

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _norm_token(t: str) -> str:
    t = t.lower().strip()
    # very light singularization: folders -> folder
    if t.endswith("s") and len(t) > 3:
        t2 = t[:-1]
        # avoid turning "ios" -> "io"
        if t2 not in {"io"}:
            t = t2
    return t


def _tokenize(text: str) -> list[str]:
    return [_norm_token(m.group(0)) for m in _WORD_RE.finditer(text or "")]


def _token_set(texts: Iterable[str]) -> set[str]:
    s: set[str] = set()
    for t in texts:
        for tok in _tokenize(t):
            if tok:
                s.add(tok)
    return s


def infer_content_mode(*, products: list[dict], intro: str, picks: list[str], alternatives: str | None) -> str:
    """
    Infer whether the content is physical, digital, or mixed based on simple term signals.
    This does not depend on category, only on actual content.
    """
    corpus_texts: list[str] = [intro, *(picks or [])]
    if alternatives:
        corpus_texts.append(alternatives)

    for p in products or []:
        corpus_texts.append(str(p.get("title", "")))
        corpus_texts.append(str(p.get("description", "")))

    tokens = _token_set(corpus_texts)

    digital_hits = len(tokens.intersection({_norm_token(x) for x in _DIGITAL_SIGNAL_TERMS}))
    physical_hits = len(tokens.intersection({_norm_token(x) for x in _PHYSICAL_SIGNAL_TERMS}))

    # Conservative defaults:
    if digital_hits > 0 and physical_hits > 0:
        return "mixed"
    if digital_hits > 0 and physical_hits == 0:
        return "digital_only"
    # Default to physical because many posts are physical goods lists
    return "physical_only"


def validate_title_semantics(
    *,
    title: str,
    products: list[dict],
    intro: str,
    picks: list[str],
    alternatives: str | None,
) -> TitleValidationResult:
    """
    Deterministic semantic validator:
    - Infers content mode (physical/digital/mixed) from the body.
    - Rejects titles that claim digital-only terms when the content is physical-only, and vice versa.
    - Rejects titles that include claim-tokens not supported by corpus.
    """
    reasons: list[str] = []

    mode = infer_content_mode(products=products, intro=intro, picks=picks, alternatives=alternatives)

    # Build evidence corpus tokens
    corpus_texts: list[str] = [intro, *(picks or [])]
    if alternatives:
        corpus_texts.append(alternatives)

    for p in products or []:
        corpus_texts.append(str(p.get("title", "")))
        corpus_texts.append(str(p.get("description", "")))

    corpus_tokens = _token_set(corpus_texts)
    title_tokens = set(_tokenize(title))

    # Mode constraints
    if mode == "physical_only":
        # Title should not strongly claim digital-first
        if title_tokens.intersection({_norm_token(x) for x in _DIGITAL_SIGNAL_TERMS}):
            # allow neutral "tools" if it's actually in corpus
            if "tool" not in title_tokens and "tools" not in title_tokens:
                reasons.append("Title implies digital tools/apps, but content appears physical-only.")
            else:
                # If title uses "tools" in a digital sense, still risk; we treat as warning only
                pass

        # Extra strict: ban "app/apps/software/platform/template/spreadsheet" claims unless present in corpus
        for tok in {"app", "apps", "software", "platform", "platforms", "template", "templates", "spreadsheet", "spreadsheets"}:
            if tok in title_tokens and tok not in corpus_tokens:
                reasons.append(f"Title includes '{tok}', but the post does not mention it.")

    elif mode == "digital_only":
        # Content is digital-only: reject physical claims like gear/supplies unless present
        for tok in {"gear", "hardware", "device", "devices", "supplies", "equipment"}:
            if tok in title_tokens and tok not in corpus_tokens:
                reasons.append(f"Title includes '{tok}', but the post does not mention physical items.")

    # Evidence constraints for claim tokens in any mode
    for tok in _CLAIM_TOKENS_REQUIRING_EVIDENCE:
        nt = _norm_token(tok)
        if nt in title_tokens and nt not in corpus_tokens:
            # "gear" is often generic; still require evidence to prevent mismatch
            reasons.append(f"Title claims '{nt}', but it is not supported by the post content.")

    ok = len(reasons) == 0
    return TitleValidationResult(ok=ok, reasons=reasons, inferred_mode=mode)
