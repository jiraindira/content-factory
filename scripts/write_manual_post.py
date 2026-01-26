from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from lib.env import load_env
from pipeline.manual_post_writer import ManualPostWriter

load_env()

DEFAULT_INPUT_PATH = Path("data/inputs/manual/post_input.json")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Write a manual post from post_input.json")
    p.add_argument("--input", default=str(DEFAULT_INPUT_PATH))
    p.add_argument("--date", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--debug-dir", default=None)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    post_date = args.date or date.today().isoformat()

    print("🟢 write_manual_post")
    print(f"📥 Input: {args.input}")
    print(f"📅 Date: {post_date}")
    print(f"🧪 Dry run: {args.dry_run}")
    if args.debug_dir:
        print(f"🧾 Debug artefacts: {args.debug_dir}")

    writer = ManualPostWriter()
    return writer.run(
        input_path=str(args.input),
        post_date=post_date,
        dry_run=bool(args.dry_run),
        debug_dir=str(args.debug_dir) if args.debug_dir else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
