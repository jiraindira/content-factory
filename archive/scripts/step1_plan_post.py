from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from lib.env import load_env
from pipeline.manual_post_planner import ManualPostPlanner

load_env()

DEFAULT_INPUT_PATH = Path("data/inputs/manual/post_input.json")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Step 1 (manual pipeline): plan a post from data/inputs/manual/post_input.json"
    )
    p.add_argument("--date", help="YYYY-MM-DD (defaults to today)")
    p.add_argument(
        "--input",
        default=str(DEFAULT_INPUT_PATH),
        help=f"Path to post input JSON (default: {DEFAULT_INPUT_PATH.as_posix()})",
    )
    p.add_argument("--provider-id", default=None)
    p.add_argument("--format-id", default=None)
    p.add_argument("--min-picks", type=int, default=None)
    return p.parse_args()


def main() -> int:
    args = parse_args()

    post_date = args.date or date.today().isoformat()

    planner = ManualPostPlanner()
    planner.run(
        date=post_date,
        input_path=str(args.input).strip(),
        provider_id=args.provider_id,
        format_id=args.format_id,
        min_picks=args.min_picks,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
