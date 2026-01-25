from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]

ARCHIVE_DIR = REPO_ROOT / "archive"
ARCHIVE_SCRIPTS_DIR = ARCHIVE_DIR / "scripts"

# Files we want to archive (not delete) because you may want to reference later.
ARCHIVE_CANDIDATES = [
    REPO_ROOT / "generate_post.py",
    REPO_ROOT / "hydrate_posts_from_catalog.py",
]

# Folders to remove if they exist (they should not be committed)
REMOVE_DIRS = [
    REPO_ROOT / "site" / "node_modules",
]

# Duplicate / confusing outputs dir (you already use output/)
# We'll archive it rather than deleting.
ARCHIVE_DIRS = [
    REPO_ROOT / "outputs",
]

# Package init typo fixes
INIT_RENAMES = [
    (REPO_ROOT / "lib" / "_init__.py", REPO_ROOT / "lib" / "__init__.py"),
    (REPO_ROOT / "memory" / "_init_.py", REPO_ROOT / "memory" / "__init__.py"),
]


def _iter_pycache_dirs(root: Path) -> Iterable[Path]:
    for p in root.rglob("__pycache__"):
        if p.is_dir():
            yield p


def _log(msg: str) -> None:
    print(msg)


def _ensure_dir(path: Path, dry_run: bool) -> None:
    if path.exists():
        return
    _log(f"📁 mkdir {path}")
    if not dry_run:
        path.mkdir(parents=True, exist_ok=True)


def _move(src: Path, dst: Path, dry_run: bool) -> None:
    if not src.exists():
        return
    _ensure_dir(dst.parent, dry_run=dry_run)
    _log(f"📦 move {src} -> {dst}")
    if not dry_run:
        if dst.exists():
            # Avoid overwriting accidentally; keep existing
            raise FileExistsError(f"Destination exists: {dst}")
        shutil.move(str(src), str(dst))


def _remove_dir(path: Path, dry_run: bool) -> None:
    if not path.exists():
        return
    if not path.is_dir():
        return
    _log(f"🧹 rm -r {path}")
    if not dry_run:
        shutil.rmtree(path, ignore_errors=True)


def _rename(src: Path, dst: Path, dry_run: bool) -> None:
    if not src.exists():
        return
    _ensure_dir(dst.parent, dry_run=dry_run)
    _log(f"✏️  rename {src} -> {dst}")
    if not dry_run:
        if dst.exists():
            # If dst exists already, don't clobber it.
            raise FileExistsError(f"Destination exists: {dst}")
        src.rename(dst)


def _check_git_dir() -> None:
    if not (REPO_ROOT / ".git").exists():
        # Not fatal; user may have extracted zip or be in a copy.
        _log("⚠️  No .git folder detected at repo root (continuing anyway).")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Repo cleanup: archive legacy scripts, remove bloat, fix package init typos.")
    p.add_argument("--dry-run", action="store_true", help="Print actions only; do not change anything.")
    p.add_argument("--yes", action="store_true", help="Skip the interactive prompt.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    dry_run = bool(args.dry_run)

    _check_git_dir()

    _log(f"🧼 Cleanup starting (dry_run={dry_run})")
    _log(f"📌 Repo root: {REPO_ROOT}")

    # Confirm (unless --yes or dry-run)
    if not dry_run and not args.yes:
        resp = input("Proceed with cleanup? This will MOVE/REMOVE files as described. (y/N): ").strip().lower()
        if resp not in {"y", "yes"}:
            _log("Aborted.")
            return 1

    # 1) Fix package init typos first
    for src, dst in INIT_RENAMES:
        _rename(src, dst, dry_run=dry_run)

    # 2) Archive legacy scripts (do not delete)
    _ensure_dir(ARCHIVE_SCRIPTS_DIR, dry_run=dry_run)
    for src in ARCHIVE_CANDIDATES:
        if src.exists():
            dst = ARCHIVE_SCRIPTS_DIR / src.name
            _move(src, dst, dry_run=dry_run)

    # 3) Archive confusing duplicate output folder
    for d in ARCHIVE_DIRS:
        if d.exists():
            dst = ARCHIVE_DIR / d.name
            _move(d, dst, dry_run=dry_run)

    # 4) Remove big generated dirs that should never be committed
    for d in REMOVE_DIRS:
        _remove_dir(d, dry_run=dry_run)

    # 5) Remove all __pycache__ folders
    pycaches = list(_iter_pycache_dirs(REPO_ROOT))
    for p in pycaches:
        _remove_dir(p, dry_run=dry_run)
    _log(f"🧽 Removed __pycache__ dirs: {len(pycaches)}")

    _log("✅ Cleanup done.")
    _log("Next: run your scripts using 'poetry run ...' and commit the changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
