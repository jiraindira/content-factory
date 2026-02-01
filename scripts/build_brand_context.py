from __future__ import annotations

import argparse
from pathlib import Path

from content_factory.brand_context import build_brand_context_artifact, write_brand_context_artifact
from content_factory.validation import load_brand_profile


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build BrandContextArtifact JSON for a brand.")
    parser.add_argument(
        "--brand",
        required=True,
        help="Path to brand YAML (e.g. content_factory/brands/alisa_amouage.yaml)",
    )
    args = parser.parse_args()

    repo_root = _repo_root()
    brand_path = Path(args.brand)
    if not brand_path.is_absolute():
        brand_path = repo_root / brand_path

    brand = load_brand_profile(brand_path)
    artifact = build_brand_context_artifact(brand=brand, repo_root=repo_root)
    out_path = write_brand_context_artifact(repo_root=repo_root, artifact=artifact)

    print(f"Wrote BrandContextArtifact: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
