from __future__ import annotations

import argparse
import re
from pathlib import Path


POSTS_DIR_DEFAULT = Path("site/src/content/posts")


_GENERIC_DESC_RE = re.compile(
    r"^\s*curated\s+.+?\s+picks\s+for\s+.+?\.?\s*$",
    re.IGNORECASE,
)


_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MD_COMMENT_RE = re.compile(r"<!--([\s\S]*?)-->")
_MD_TAG_RE = re.compile(r"<[^>]+>")


def _is_generic_description(description: str) -> bool:
    s = (description or "").strip()
    if not s:
        return True
    return bool(_GENERIC_DESC_RE.match(s))


def _yaml_single_quoted(value: str) -> str:
    s = (value or "").replace("\r\n", " ").replace("\n", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return "'" + s.replace("'", "''") + "'"


def _truncate_text_max_chars(text: str, max_chars: int) -> str:
    s = (text or "").strip()
    if not s:
        return s
    if len(s) <= max_chars:
        return s
    # Reserve space for an ellipsis so truncated descriptions feel intentional.
    target = max(1, max_chars - 1)
    cut = s[:target].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0].rstrip()
    cut = cut.rstrip(" .!?,;:")
    if not cut:
        return "…" if max_chars >= 1 else ""
    return cut + "…"


def _plain_text_from_markdown(md: str) -> str:
    s = (md or "").strip()
    if not s:
        return ""
    s = _MD_COMMENT_RE.sub(" ", s)
    s = _MD_LINK_RE.sub(r"\1", s)
    s = _MD_TAG_RE.sub(" ", s)
    s = s.replace("`", "").replace("*", "").replace("_", "")
    s = re.sub(r"\s+", " ", s.replace("\n", " ")).strip()
    return s


def _extract_intro_section(body_md: str) -> str:
    """Extract markdown content under '## Intro' until the next H2."""
    lines = (body_md or "").splitlines()

    start_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().lower() == "## intro":
            start_idx = i + 1
            break
    if start_idx is None:
        return ""

    end_idx = len(lines)
    for j in range(start_idx, len(lines)):
        if lines[j].strip().startswith("## "):
            end_idx = j
            break

    return "\n".join(lines[start_idx:end_idx]).strip()


def _derive_description_from_intro(intro_md: str, max_chars: int) -> str:
    txt = _plain_text_from_markdown(intro_md)
    if not txt:
        return ""

    # Prefer first sentence if it looks meaningful.
    m = re.match(r"^(.+?[.!?])\s+", txt)
    if m and 60 <= len(m.group(1)) <= max_chars:
        return m.group(1).strip()

    return _truncate_text_max_chars(txt, max_chars)


def _split_frontmatter(text: str) -> tuple[str, str, str] | None:
    """Return (frontmatter_with_delims, frontmatter_body, markdown_body) or None."""
    if not text.startswith("---"):
        return None
    lines = text.splitlines(keepends=True)
    if not lines:
        return None

    if lines[0].strip() != "---":
        return None

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None

    fm_with_delims = "".join(lines[: end + 1])
    fm_body = "".join(lines[1:end])
    md_body = "".join(lines[end + 1 :])
    return fm_with_delims, fm_body, md_body


def _get_frontmatter_value(fm_body: str, key: str) -> str | None:
    # Basic single-line extractor (good enough for description/title/audience)
    # Matches: key: "..." | key: '...' | key: bare
    pattern = re.compile(rf"(?mi)^\s*{re.escape(key)}\s*:\s*(.+?)\s*$")
    m = pattern.search(fm_body)
    if not m:
        return None

    raw = m.group(1).strip()
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    return raw


def _replace_or_insert_description(fm_body: str, new_description: str) -> str:
    lines = fm_body.splitlines()
    replaced = False

    for i, ln in enumerate(lines):
        if re.match(r"(?i)^\s*description\s*:\s*", ln):
            indent = re.match(r"^(\s*)", ln).group(1)  # type: ignore[union-attr]
            lines[i] = f"{indent}description: {_yaml_single_quoted(new_description)}"
            replaced = True
            break

    if replaced:
        return "\n".join(lines) + ("\n" if fm_body.endswith("\n") else "")

    # Insert after title if possible, else append at end.
    insert_at = None
    for i, ln in enumerate(lines):
        if re.match(r"(?i)^\s*title\s*:\s*", ln):
            insert_at = i + 1
            break

    if insert_at is None:
        lines.append(f"description: {_yaml_single_quoted(new_description)}")
    else:
        lines.insert(insert_at, f"description: {_yaml_single_quoted(new_description)}")

    return "\n".join(lines) + "\n"


def fix_file(path: Path, *, max_chars: int, dry_run: bool, force: bool) -> bool:
    original = path.read_text(encoding="utf-8")
    split = _split_frontmatter(original)
    if split is None:
        return False

    _fm_with_delims, fm_body, md_body = split

    current_description = _get_frontmatter_value(fm_body, "description") or ""
    if not force and not _is_generic_description(current_description):
        return False

    intro_md = _extract_intro_section(md_body)
    new_description = _derive_description_from_intro(intro_md, max_chars=max_chars)
    if not new_description:
        return False

    new_fm_body = _replace_or_insert_description(fm_body, new_description)
    if new_fm_body == fm_body:
        return False

    # Reconstruct file preserving original delimiter/newline formatting.
    # Always normalize to:
    # ---\n{frontmatter}\n---\n\n{body...}
    new_text = "---\n" + new_fm_body + "---\n" + md_body.lstrip("\r\n")

    if dry_run:
        return True

    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Replace boilerplate post descriptions with Intro excerpts")
    parser.add_argument("--posts-dir", default=str(POSTS_DIR_DEFAULT), help="Path to posts directory")
    parser.add_argument("--max-chars", type=int, default=160, help="Max description length")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Also overwrite non-generic descriptions (use with care)",
    )

    args = parser.parse_args()

    posts_dir = Path(args.posts_dir)
    if not posts_dir.exists():
        raise FileNotFoundError(f"posts dir not found: {posts_dir}")

    changed = 0
    scanned = 0

    for path in sorted(posts_dir.glob("*.md")):
        scanned += 1
        if fix_file(path, max_chars=args.max_chars, dry_run=args.dry_run, force=args.force):
            changed += 1
            print(f"UPDATED: {path.as_posix()}")

    print(f"Scanned {scanned} file(s), updated {changed}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
