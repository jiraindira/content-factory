from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts-dir", default="site/src/content/posts", help="Directory of posts (md/mdx)")
    ap.add_argument("--provider", default="amazon_uk", help="Provider id (default amazon_uk)")
    ap.add_argument("--dry-run", action="store_true", help="Print files that would be hydrated (no writes)")
    args = ap.parse_args()

    posts_dir = Path(args.posts_dir)
    if not posts_dir.exists():
        raise SystemExit(f"Posts dir not found: {posts_dir}")

    files = sorted(list(posts_dir.rglob("*.md")) + list(posts_dir.rglob("*.mdx")))
    if not files:
        raise SystemExit(f"No markdown files found under: {posts_dir}")

    if args.dry_run:
        for fp in files:
            print(fp.as_posix())
        print(f"Scanned: {len(files)} files (dry-run)")
        return

    ok = 0
    failed = 0

    for fp in files:
        cmd = [
            sys.executable,
            str(Path("scripts") / "hydrate_post.py"),
            "--post",
            str(fp),
            "--provider",
            args.provider,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            ok += 1
            # keep output short but useful
            line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else f"✅ {fp}"
            print(line)
        else:
            failed += 1
            print(f"[FAIL] {fp}")
            if r.stdout:
                print(r.stdout.strip())
            if r.stderr:
                print(r.stderr.strip())

    print(f"Done. Updated: {ok}, Failed: {failed}, Total: {len(files)}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
