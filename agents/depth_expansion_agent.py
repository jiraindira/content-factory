from __future__ import annotations

import os
import re
from typing import Any

from agents.base import BaseAgent
from agents.llm_client import LLMClient
from schemas.depth import (
    AppliedModule,
    DepthExpansionInput,
    DepthExpansionOutput,
    ExpansionModuleSpec,
    RewriteMode,
)
from styles.site_style import get_style_profile


def normalize_markdown_bullets(text: str) -> str:
    """
    Ensure '- ' bullets start on their own lines.
    Fixes cases where the model outputs: 'Sentence - bullet - bullet'
    """
    s = (text or "").strip()

    # Newline before any " - " that looks like a bullet marker.
    # This is intentionally conservative: it only targets " - " (space-dash-space).
    s = re.sub(r"(?<!\n)\s-\s", "\n- ", s)

    # Cleanup: prevent massive blank runs
    s = re.sub(r"\n{3,}", "\n\n", s)

    return s.strip()


def estimate_word_count(text: str) -> int:
    return len((text or "").strip().split())


def normalize_ws(text: str) -> str:
    return "\n".join([line.rstrip() for line in (text or "").splitlines()]).strip() + "\n"


def clamp_words(text: str, max_words: int) -> str:
    words = (text or "").split()
    if max_words <= 0 or len(words) <= max_words:
        return (text or "").strip()
    return " ".join(words[:max_words]).strip() + "…"


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _sanitize_text(text: str, banned_phrases: list[str]) -> str:
    out = text or ""
    low = out.lower()
    for bp in banned_phrases or []:
        bpl = (bp or "").lower().strip()
        if not bpl:
            continue
        if bpl in low:
            out = out.replace(bp, "").replace(bp.title(), "").replace(bp.upper(), "")
            low = out.lower()
    return " ".join(out.split()).strip()


# -------------------------
# Placeholder helpers
# -------------------------

INTRO_TOKEN = "{{INTRO}}"
HOW_TOKEN = "{{HOW_WE_CHOSE}}"
ALT_TOKEN = "{{ALTERNATIVES}}"

PICK_RE = re.compile(r"\{\{PICK:([^\}]+)\}\}")


def _has_placeholder(md: str, token: str) -> bool:
    return token in (md or "")


def _replace_placeholder(md: str, token: str, replacement: str) -> str:
    # Replace exactly once; if the token appears multiple times, that’s a structural bug.
    return (md or "").replace(token, replacement.strip(), 1)


def _extract_pick_ids_in_order(md: str) -> list[str]:
    return [m.group(1).strip() for m in PICK_RE.finditer(md or "") if m.group(1).strip()]


def _replace_pick_placeholder(md: str, pick_id: str, replacement: str) -> str:
    token = f"{{{{PICK:{pick_id}}}}}"
    return (md or "").replace(token, replacement.strip(), 1)


def _extract_frontmatter_value(md: str, key: str) -> str:
    """
    Minimal YAML frontmatter reader for simple key: "value" lines.
    We keep it deterministic and avoid full YAML parsing.
    """
    text = md or ""
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return ""
    # find end fence
    start = text.find("---")
    end = text.find("\n---", start + 3)
    if end == -1:
        return ""
    fm = text[start : end + 4]
    # match key: "..."
    pat = re.compile(rf'^{re.escape(key)}:\s*"(.*)"\s*$', re.MULTILINE)
    m = pat.search(fm)
    return (m.group(1).strip() if m else "")


class DepthExpansionAgent(BaseAgent):
    """
    DepthExpansionAgent (placeholder-driven)

    PASS 1: AUTHORING
      - Generates content for placeholders:
        {{INTRO}}, {{HOW_WE_CHOSE}}, {{PICK:<id>}}..., {{ALTERNATIVES}}
      - Replaces placeholders in-place.

    PASS 2: EDITING (optional)
      - Whole-doc sweep for flow/formatting/voice consistency.
      - Preserves YAML frontmatter and does not alter URLs.
      - Does not add testing claims.
      - Controlled by env DEPTH_ENABLE_EDIT_PASS (default: on).
    """

    name = "depth-expansion"

    def __init__(self) -> None:
        self.llm = LLMClient()

    def run(self, input: DepthExpansionInput | dict) -> dict[str, Any]:
        inp = input if isinstance(input, DepthExpansionInput) else DepthExpansionInput(**input)

        category = self._infer_category_from_draft(inp)
        profile = get_style_profile(category=category, voice=inp.voice)

        before_wc = estimate_word_count(inp.draft_markdown)
        expanded = normalize_ws(inp.draft_markdown)

        applied: list[AppliedModule] = []

        # -------------------------
        # PASS 1: AUTHORING (placeholders)
        # -------------------------
        for module in inp.modules:
            if not module.enabled:
                continue

            mode: RewriteMode = module.rewrite_mode or inp.rewrite_mode
            expanded_before = expanded

            if module.name == "intro":
                expanded, meta = self._apply_intro(inp, expanded, module, profile, mode)
            elif module.name == "how_we_chose":
                expanded, meta = self._apply_how_we_chose_placeholder(inp, expanded, module, profile, mode)
            elif module.name == "product_writeups":
                expanded, meta = self._apply_product_writeups(inp, expanded, module, profile, mode)
            elif module.name == "alternatives":
                expanded, meta = self._apply_alternatives_placeholder(inp, expanded, module, profile, mode)
            else:
                continue

            added_est = max(0, estimate_word_count(expanded) - estimate_word_count(expanded_before))
            applied.append(
                AppliedModule(
                    name=module.name,
                    added_words_estimate=int(meta.get("added_words_estimate", added_est)),
                    notes=str(meta.get("notes", "") or ""),
                )
            )

            if (estimate_word_count(expanded) - before_wc) >= inp.max_added_words:
                break

        # Safety: never ship raw placeholders
        expanded = self._final_placeholder_safety(expanded)

        # -------------------------
        # PASS 2: EDITING (optional)
        # -------------------------
        enable_edit_pass = _env_flag("DEPTH_ENABLE_EDIT_PASS", default=True)
        added_so_far = estimate_word_count(expanded) - before_wc

        if enable_edit_pass and inp.rewrite_mode == "upgrade" and added_so_far < inp.max_added_words:
            edited = self._edit_pass(inp=inp, md=expanded, profile=profile, category=category)
            if estimate_word_count(edited) - before_wc <= inp.max_added_words:
                if edited.strip() != expanded.strip():
                    expanded = normalize_ws(edited)
                    applied.append(
                        AppliedModule(
                            name="edit_pass",
                            added_words_estimate=max(
                                0, estimate_word_count(expanded) - estimate_word_count(expanded_before)
                            ),
                            notes="Applied whole-document editor pass (upgrade).",
                        )
                    )

        after_wc = estimate_word_count(expanded)

        out = DepthExpansionOutput(
            expanded_markdown=expanded.strip() + "\n",
            applied_modules=applied,
            word_count_before=before_wc,
            word_count_after=after_wc,
        )
        return out.to_dict()

    def _final_placeholder_safety(self, md: str) -> str:
        """
        Ensure we never publish raw placeholder tokens.
        Deterministic fallbacks only.
        """
        out = md or ""
        if INTRO_TOKEN in out:
            out = out.replace(INTRO_TOKEN, "A short, practical guide to the picks below.", 1)
        if HOW_TOKEN in out:
            out = out.replace(HOW_TOKEN, "Everything here was chosen to be practical and easy to use.", 1)
        if ALT_TOKEN in out:
            out = out.replace(
                ALT_TOKEN, "If none of these fit, consider a simpler or cheaper version of the same idea.", 1
            )
        # PICK placeholders: remove any remaining with a neutral line
        out = PICK_RE.sub("A practical option for this guide. (Details coming soon.)", out)
        return out

    # -------------------------
    # Category inference
    # -------------------------

    def _infer_category_from_draft(self, inp: DepthExpansionInput) -> str:
        md = inp.draft_markdown or ""
        marker = 'category: "'
        if marker in md:
            start = md.find(marker) + len(marker)
            end = md.find('"', start)
            if end != -1:
                val = md[start:end].strip()
                return val or "general"
        return "general"

    # -------------------------
    # LLM authoring helpers
    # -------------------------

    def _llm_author(
        self,
        *,
        category: str,
        profile: dict,
        inp: DepthExpansionInput,
        max_words: int,
        intent: str,
        format_hint: str = "",
        context: str = "",
    ) -> str:
        banned = profile.get("banned_phrases", []) or []
        forbidden = profile.get("forbidden_terms", []) or []
        preferred = profile.get("preferred_terms", []) or []
        golden = (profile.get("golden_post_excerpt") or "").strip()

        products = inp.products or []
        product_bullets = "\n".join([f"- {p.get('title','')}: {p.get('description','')}" for p in products[:8]])

        system = (
            "You are writing a blog buying guide in a human, lightly witty voice. "
            "Be concise. Avoid corporate SEO tone. Be specific and practical."
        )

        user = f"""
INTENT:
{intent}

CATEGORY: {category}

STYLE REFERENCE (do NOT copy verbatim, just match the vibe):
{golden if golden else "(none)"}

CONSTRAINTS:
- Slightly quirky/observational, but not long-winded.
- No hype. No “best ever”. No exaggerated promises.
- Do NOT claim hands-on testing.
- Do NOT invent product features beyond what is implied by name/description.
- Keep it skimmable.
- Output ONLY the requested content (no headings unless asked).
- Max about {max_words} words.

BANNED PHRASES (avoid):
{", ".join(banned) if banned else "(none)"}

FORBIDDEN TERMS (do not include):
{", ".join(forbidden) if forbidden else "(none)"}

PREFERRED TERMS (use only if natural):
{", ".join(preferred) if preferred else "(none)"}

PRODUCT CONTEXT:
{product_bullets if product_bullets.strip() else "(no products provided)"}

ADDITIONAL CONTEXT:
{context.strip() if context.strip() else "(none)"}

{format_hint}
""".strip()

        text = self.llm.generate_text(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            seed=1337,
            reasoning_effort="low",
        )

        text = _sanitize_text(text, banned)
        text = clamp_words(text, max_words)
        return text.strip()

    # -------------------------
    # PASS 2: Editing
    # -------------------------

    def _split_frontmatter(self, md: str) -> tuple[str, str]:
        text = md or ""
        stripped = text.lstrip()
        if not stripped.startswith("---"):
            return "", text

        start = text.find("---")
        end = text.find("\n---", start + 3)
        if end == -1:
            return "", text
        end2 = text.find("\n", end + 4)
        if end2 == -1:
            return "", text

        fm = text[: end2 + 1]
        body = text[end2 + 1 :]
        return fm, body

    def _edit_pass(self, *, inp: DepthExpansionInput, md: str, profile: dict, category: str) -> str:
        banned = profile.get("banned_phrases", []) or []
        forbidden = profile.get("forbidden_terms", []) or []
        preferred = profile.get("preferred_terms", []) or []
        golden = (profile.get("golden_post_excerpt") or "").strip()

        frontmatter, body = self._split_frontmatter(md)

        system = (
            "You are a sharp but kind editor. You polish posts to feel human and readable. "
            "You tighten repetition and improve flow without changing meaning."
        )

        user = f"""
You are editing ONLY the markdown BODY of a blog post.

GOALS:
- Improve flow and readability.
- Keep the voice personal/lightly witty, but concise.
- Ensure bullets are properly formatted (one per line).
- Reduce repetition and filler.
- Keep it skimmable.

HARD RULES:
- DO NOT change YAML frontmatter (you won't see it).
- DO NOT change any URLs.
- DO NOT add claims of hands-on testing.
- DO NOT add new sections or headings beyond what exists.
- Do not invent product features.
- Output ONLY the edited markdown BODY (no frontmatter).

CATEGORY: {category}

STYLE REFERENCE (do NOT copy verbatim, just match vibe):
{golden if golden else "(none)"}

BANNED PHRASES:
{", ".join(banned) if banned else "(none)"}

FORBIDDEN TERMS:
{", ".join(forbidden) if forbidden else "(none)"}

PREFERRED TERMS:
{", ".join(preferred) if preferred else "(none)"}

MARKDOWN BODY TO EDIT:
{body.strip()}
""".strip()

        edited_body = self.llm.generate_text(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            seed=1337,
            reasoning_effort="low",
        )

        edited_body = _sanitize_text(edited_body, banned)
        edited_body = normalize_markdown_bullets(edited_body)
        edited_body = normalize_ws(edited_body)

        if frontmatter:
            return frontmatter.rstrip() + "\n\n" + edited_body.lstrip("\n")
        return edited_body

    # -------------------------
    # Placeholder modules
    # -------------------------

    def _apply_intro(
        self,
        inp: DepthExpansionInput,
        md: str,
        module: ExpansionModuleSpec,
        profile: dict,
        mode: RewriteMode,
    ):
        category = self._infer_category_from_draft(inp)
        if not _has_placeholder(md, INTRO_TOKEN):
            return md, {"added_words_estimate": 0, "notes": "INTRO placeholder not found; skipped."}

        if mode != "upgrade":
            title = _extract_frontmatter_value(md, "title") or "this guide"
            audience = _extract_frontmatter_value(md, "audience")
            base = f"This guide covers {title.lower()}."
            if audience:
                base += f" It’s for {audience.strip()}."
            base = clamp_words(base, module.max_words)
            new_md = _replace_placeholder(md, INTRO_TOKEN, base)
            return new_md, {
                "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
                "notes": f"Filled INTRO ({mode}).",
            }

        title = _extract_frontmatter_value(md, "title")
        audience = _extract_frontmatter_value(md, "audience")
        context = f'TITLE: "{title}"\nAUDIENCE: "{audience}"'
        intent = (
            "Write a short intro (3–4 sentences). Situational, lightly funny/observational, not dry. "
            "Promise a short practical list. Do not mention 'affiliate' or 'SEO'."
        )

        text = self._llm_author(
            category=category,
            profile=profile,
            inp=inp,
            max_words=module.max_words,
            intent=intent,
            context=context,
        )
        new_md = _replace_placeholder(md, INTRO_TOKEN, text)
        return new_md, {
            "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
            "notes": "Filled INTRO (upgrade).",
        }

    def _apply_how_we_chose_placeholder(
        self,
        inp: DepthExpansionInput,
        md: str,
        module: ExpansionModuleSpec,
        profile: dict,
        mode: RewriteMode,
    ):
        category = self._infer_category_from_draft(inp)
        if not _has_placeholder(md, HOW_TOKEN):
            return md, {"added_words_estimate": 0, "notes": "HOW_WE_CHOSE placeholder not found; skipped."}

        if mode != "upgrade":
            body = "\n".join(
                [
                    "Everything here was chosen to be practical and low-fuss:",
                    "",
                    "- Works in real homes (space and cleanup matter).",
                    "- Easy to set up and put away.",
                    "- Holds up to repeat use.",
                    "- Useful for the audience and season.",
                ]
            )
            body = clamp_words(body, module.max_words)
            body = normalize_markdown_bullets(body)
            new_md = _replace_placeholder(md, HOW_TOKEN, body)
            return new_md, {
                "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
                "notes": f"Filled HOW_WE_CHOSE ({mode}).",
            }

        title = _extract_frontmatter_value(md, "title")
        audience = _extract_frontmatter_value(md, "audience")
        context = f'TITLE: "{title}"\nAUDIENCE: "{audience}"'
        intent = (
            "Write 'How this list was chosen' as a short intro sentence plus 4–6 bullet points. "
            "Bullets should be concrete and practical. Keep it brief and human."
        )
        format_hint = "FORMAT:\n- One short intro sentence\n- Then 4–6 bullets, one per line"

        text = self._llm_author(
            category=category,
            profile=profile,
            inp=inp,
            max_words=module.max_words,
            intent=intent,
            format_hint=format_hint,
            context=context,
        )
        text = normalize_markdown_bullets(text)
        new_md = _replace_placeholder(md, HOW_TOKEN, text)
        return new_md, {
            "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
            "notes": "Filled HOW_WE_CHOSE (upgrade).",
        }

    def _apply_product_writeups(
        self,
        inp: DepthExpansionInput,
        md: str,
        module: ExpansionModuleSpec,
        profile: dict,
        mode: RewriteMode,
    ):
        category = self._infer_category_from_draft(inp)
        pick_ids = _extract_pick_ids_in_order(md)
        if not pick_ids:
            return md, {"added_words_estimate": 0, "notes": "No PICK placeholders found; skipped."}

        products = list(inp.products or [])
        if not products:
            return md, {"added_words_estimate": 0, "notes": "No products provided; skipped."}

        count = min(len(pick_ids), len(products))
        per_pick_budget = max(45, min(120, int(module.max_words / max(1, count))))

        expanded = md
        for i in range(count):
            pick_id = pick_ids[i]
            p = products[i]
            title = (p.get("title") or "").strip()
            desc = (p.get("description") or "").strip()

            if mode != "upgrade":
                fallback = desc or "A practical pick that fits the theme of this guide."
                fallback = clamp_words(fallback, per_pick_budget)
                expanded = _replace_pick_placeholder(expanded, pick_id, fallback)
                continue

            context = f'PRODUCT: "{title}"\nKNOWN DESCRIPTION: "{desc}"'
            intent = (
                "Write ONE paragraph (2–4 sentences). "
                "Sentence 1: why it’s a good fit for this guide. "
                "Sentence 2: what it’s best for in real life. "
                "Sentence 3 (optional): a clear tradeoff or who should skip it. "
                "No testing claims. No hype. No made-up specs."
            )

            text = self._llm_author(
                category=category,
                profile=profile,
                inp=inp,
                max_words=per_pick_budget,
                intent=intent,
                context=context,
            )
            expanded = _replace_pick_placeholder(expanded, pick_id, text)

        for j in range(count, len(pick_ids)):
            expanded = _replace_pick_placeholder(
                expanded,
                pick_ids[j],
                "A practical option for this guide. (Details coming soon.)",
            )

        return expanded, {
            "added_words_estimate": max(0, estimate_word_count(expanded) - estimate_word_count(md)),
            "notes": f"Filled {count} product writeups ({mode}).",
        }

    def _apply_alternatives_placeholder(
        self,
        inp: DepthExpansionInput,
        md: str,
        module: ExpansionModuleSpec,
        profile: dict,
        mode: RewriteMode,
    ):
        category = self._infer_category_from_draft(inp)
        if not _has_placeholder(md, ALT_TOKEN):
            return md, {"added_words_estimate": 0, "notes": "ALTERNATIVES placeholder not found; skipped."}

        if mode != "upgrade":
            body = "\n".join(
                [
                    "If the main picks aren’t quite right, consider:",
                    "",
                    "- A cheaper, simpler version of the same idea.",
                    "- A smaller option if storage is tight.",
                    "- A quieter alternative if noise is a problem.",
                ]
            )
            body = clamp_words(body, module.max_words)
            body = normalize_markdown_bullets(body)
            new_md = _replace_placeholder(md, ALT_TOKEN, body)
            return new_md, {
                "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
                "notes": f"Filled ALTERNATIVES ({mode}).",
            }

        title = _extract_frontmatter_value(md, "title")
        audience = _extract_frontmatter_value(md, "audience")
        context = f'TITLE: "{title}"\nAUDIENCE: "{audience}"'
        intent = (
            "Write a short 'Alternatives worth considering' section: 1 short intro sentence, then 3–5 bullets. "
            "Focus on real-world constraints (budget, space, noise, simplicity). Keep it brief."
        )
        format_hint = "FORMAT:\n- One short intro sentence\n- Then 3–5 bullets, one per line"

        text = self._llm_author(
            category=category,
            profile=profile,
            inp=inp,
            max_words=module.max_words,
            intent=intent,
            format_hint=format_hint,
            context=context,
        )
        text = normalize_markdown_bullets(text)
        new_md = _replace_placeholder(md, ALT_TOKEN, text)
        return new_md, {
            "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
            "notes": "Filled ALTERNATIVES (upgrade).",
        }
