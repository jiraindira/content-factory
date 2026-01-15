from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from integrations.openai_adapters import OpenAIJsonLLM


@dataclass(frozen=True)
class PostRepairConfig:
    max_changes: int = 12  # safety rail: avoid full rewrites


def _extract_missing_skip_pick_numbers(qa_report: dict[str, Any]) -> list[int]:
    """
    Pull missing_pick_numbers from RULE_MISSING_SKIP_IT_IF issue meta.
    qa_report is a dict produced by PreflightQAReport.model_dump().
    """
    issues = qa_report.get("issues", [])
    if not isinstance(issues, list):
        return []

    for it in issues:
        if not isinstance(it, dict):
            continue
        if it.get("rule_id") != "RULE_MISSING_SKIP_IT_IF":
            continue
        meta = it.get("meta", {})
        if isinstance(meta, dict):
            nums = meta.get("missing_pick_numbers", [])
            if isinstance(nums, list):
                out: list[int] = []
                for n in nums:
                    try:
                        out.append(int(n))
                    except Exception:
                        pass
                return out
    return []


class PostRepairAgent:
    """
    Repairs a markdown draft based on a QA report.
    Only makes targeted fixes for the failing rules.
    """

    def __init__(self, *, llm: OpenAIJsonLLM, config: PostRepairConfig | None = None) -> None:
        self._llm = llm
        self._cfg = config or PostRepairConfig()

    def run(
        self,
        *,
        draft_markdown: str,
        qa_report: dict[str, Any],
        products: list[dict],
        intro_text: str,
        picks_texts: list[str],
    ) -> dict[str, Any]:
        """
        Returns:
          {
            "repaired_markdown": "...",
            "changes_made": [ ... ],
          }
        """
        missing_skip_picks = _extract_missing_skip_pick_numbers(qa_report)

        system = (
            "You are a precise editor repairing a markdown blog post draft.\n"
            "Your goal is to fix ONLY the issues listed in the QA report.\n"
            "\n"
            "Hard rules:\n"
            "- Make minimal edits. Do not rewrite the whole post.\n"
            "- Do not invent product specs, prices, ratings, certifications, or performance claims.\n"
            "- Do not claim personal experience, hands-on testing, or 'we tested' language.\n"
            "- Keep the tone consistent.\n"
            f"- Make no more than {self._cfg.max_changes} discrete changes.\n"
            "- Keep the frontmatter block intact unless a frontmatter rule failed.\n"
            "- Do not change file paths, slugs, headings hierarchy, or section ordering.\n"
            "\n"
            "Return STRICT JSON with keys:\n"
            '  repaired_markdown: string\n'
            '  changes_made: array of short strings\n'
        )

        # Very explicit repair directives for the most common failure:
        # make the phrase matching deterministic for QA.
        skip_fix_directive = ""
        if missing_skip_picks:
            skip_fix_directive = (
                "RULE_MISSING_SKIP_IT_IF FIX INSTRUCTIONS:\n"
                f"- The QA report says these pick numbers are missing skip-guidance: {missing_skip_picks}\n"
                "- For EACH of those picks, add exactly ONE new sentence that contains the exact substring "
                "'Skip it if' (case-sensitive) inside that pick's paragraph block.\n"
                "- The sentence should be truthful and generic (avoid specific specs). Examples:\n"
                "  - 'Skip it if you only need this occasionally and would rather borrow or go smaller.'\n"
                "  - 'Skip it if your pet stays indoors and you don't need the extra protection.'\n"
                "- Do not add 'Skip it if' anywhere else (not in intro, not in alternatives).\n"
            )

        user = {
            "qa_report": qa_report,
            "missing_skip_pick_numbers": missing_skip_picks,
            "products": products,
            "intro_excerpt": (intro_text or "")[:600],
            # Provide all picks excerpts to help it locate which ones to edit
            "picks_excerpts": [(p or "")[:700] for p in (picks_texts or [])],
            "draft_markdown": draft_markdown,
            "instructions": (
                "Fix the QA failures using minimal edits.\n"
                f"{skip_fix_directive}\n"
                "Other fixes:\n"
                "- If RULE_UNRESOLVED_PLACEHOLDERS: replace remaining {{...}} placeholders with appropriate content.\n"
                "- If RULE_FORBIDDEN_TESTING_CLAIMS: rephrase to avoid testing/review claims.\n"
                "- If RULE_MISSING_SPACE_AFTER_PUNCT (warning): fix obvious missing spaces.\n"
                "\n"
                "Important: keep the post structure and headings the same.\n"
            ),
        }

        data = self._llm.complete_json(system=system, user=str(user))

        repaired = data.get("repaired_markdown")
        if not isinstance(repaired, str) or not repaired.strip():
            return {"repaired_markdown": draft_markdown, "changes_made": ["(repair failed: returned empty output)"]}

        changes = data.get("changes_made", [])
        if not isinstance(changes, list):
            changes = []

        changes = [c for c in changes if isinstance(c, str)][: self._cfg.max_changes]

        return {"repaired_markdown": repaired, "changes_made": changes}
