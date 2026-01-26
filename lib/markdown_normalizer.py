from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class MarkdownNormalizeConfig:
    section_headings: tuple[str, ...] = (
        "Intro",
        "How this list was chosen",
        "The picks",
        # Intentionally NO "Alternatives worth considering"
    )


def _collapse_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _starts_with(a: str, b: str) -> bool:
    return _collapse_spaces(a).lower().startswith(_collapse_spaces(b).lower())


def normalize_markdown(
    md: str,
    *,
    product_titles: Iterable[str] = (),
    config: MarkdownNormalizeConfig | None = None,
) -> str:
    """
    Deterministic formatter for LLM outputs that glue headings to paragraphs.

    Guarantees:
      - Any '## ' or '### ' token starts on its own line
      - Headings are followed by a blank line (unless immediately followed by another heading/comment/hr)
      - Known section headings and product headings are split from inline text:
          '## Intro blah' -> '## Intro\\n\\nblah'
          '### Product blah' -> '### Product\\n\\nblah'

    Note:
      - We only “special split” headings listed in config.section_headings.
      - If you don't want a section to exist, do not include it here.
    """
    cfg = config or MarkdownNormalizeConfig()
    text = (md or "").replace("\r\n", "\n").replace("\r", "\n")

    # 1) If a heading marker appears mid-line, force it onto a new line.
    #    Example: "blah. ## Intro ..." -> "blah.\n\n## Intro ..."
    text = re.sub(r"([^\n])\s*(#{2,6}\s+)", r"\1\n\n\2", text)

    # 2) Split known section headings when they have inline content on same line.
    for h in cfg.section_headings:
        if not (h or "").strip():
            continue
        pat = rf"(?m)^(##\s+{re.escape(h)})\s+(?P<rest>\S.+)$"
        text = re.sub(pat, r"\1\n\n\g<rest>", text)

    # 3) Split product headings when they have inline content on same line.
    #    Robust match: if heading text starts with the title (collapsed spaces), split it.
    titles = [t for t in (product_titles or []) if (t or "").strip()]
    if titles:
        lines = text.splitlines()
        out: list[str] = []

        for line in lines:
            if line.startswith("### "):
                after = line[4:].strip()
                matched_title = None
                for t in titles:
                    if _starts_with(after, t) and _collapse_spaces(after).lower() != _collapse_spaces(t).lower():
                        matched_title = t
                        break
                if matched_title:
                    # Keep heading text as-is up to the end of the title, then blank line, then remainder.
                    m = re.match(
                        re.escape(matched_title).replace(r"\ ", r"\s+"),
                        after,
                        flags=re.IGNORECASE,
                    )
                    if m:
                        head = after[: m.end()].strip()
                        rest = after[m.end() :].strip()
                        if rest:
                            out.append(f"### {head}")
                            out.append("")
                            out.append(rest)
                            continue

                    # Fallback: use the provided title literally
                    rest2 = _collapse_spaces(after)[len(_collapse_spaces(matched_title)) :].strip()
                    out.append(f"### {matched_title}")
                    if rest2:
                        out.append("")
                        out.append(rest2)
                    continue

            out.append(line)

        text = "\n".join(out)

    # 4) Ensure a blank line after any heading if followed immediately by text/comment/hr.
    text = re.sub(
        r"(?m)^(#{2,6}\s+.+)\n(?!\s*$)(?!#{2,6}\s)(?!<!--)(?!<hr\s*/?>)([^\n])",
        r"\1\n\n\2",
        text,
    )

    # 5) Make sure HTML comments and <hr /> are not glued to text on same line.
    text = re.sub(r"([^\n])\s*(<!--\s*pick_id:)", r"\1\n\2", text)
    text = re.sub(r"([^\n])\s*(<hr\s*/?>)", r"\1\n\n\2", text)

    return text
