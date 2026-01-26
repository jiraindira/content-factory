from __future__ import annotations

import argparse

from lib.env import load_env
from pipeline.manual_catalog_applier import ManualCatalogApplier

load_env()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Step 2 (manual pipeline): apply manual catalog metadata into the plan.")
    p.add_argument("--post-slug", required=True, help="e.g. 2026-01-23-some-slug")
    p.add_argument("--min-picks", type=int, default=None, help="Default: 6")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    applier = ManualCatalogApplier()
    applier.run(post_slug=str(args.post_slug).strip(), min_picks=args.min_picks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
