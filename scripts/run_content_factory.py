from __future__ import annotations

import argparse
from pathlib import Path

from content_factory.adapters.dispatch import render_for_request, write_delivery
from content_factory.artifact_io import write_content_artifact
from content_factory.artifact_validation import validate_artifact_against_specs
from content_factory.brand_context import BrandContextArtifact, artifact_path_for_brand
from content_factory.compiler import compile_content_artifact
from content_factory.validation import load_brand_profile, load_content_request, validate_request_against_brand


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_brand_context(*, repo_root: Path, brand_id: str) -> BrandContextArtifact:
    p = artifact_path_for_brand(repo_root=repo_root, brand_id=brand_id)
    if not p.exists():
        raise FileNotFoundError(
            f"BrandContextArtifact not found: {p}. Run scripts/build_brand_context.py first."
        )
    return BrandContextArtifact.model_validate_json(p.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the spec-driven content factory compiler.")
    parser.add_argument("--brand", required=True, help="Path to brand YAML")
    parser.add_argument("--request", required=True, help="Path to request YAML")
    parser.add_argument("--run-id", required=False, help="Optional run id override")
    args = parser.parse_args()

    repo_root = _repo_root()

    brand_path = Path(args.brand)
    if not brand_path.is_absolute():
        brand_path = repo_root / brand_path

    request_path = Path(args.request)
    if not request_path.is_absolute():
        request_path = repo_root / request_path

    brand = load_brand_profile(brand_path)
    request = load_content_request(request_path)
    validate_request_against_brand(brand=brand, request=request)

    ctx = _load_brand_context(repo_root=repo_root, brand_id=brand.brand_id)

    run_id = args.run_id or request_path.stem

    artifact = compile_content_artifact(
        brand=brand,
        request=request,
        brand_context=ctx,
        run_id=run_id,
    )

    validate_artifact_against_specs(brand=brand, request=request, artifact=artifact)
    out_path = write_content_artifact(repo_root=repo_root, artifact=artifact)

    delivery = render_for_request(brand=brand, request=request, artifact=artifact)
    delivery_path = write_delivery(repo_root=repo_root, delivery=delivery)

    print(f"Wrote ContentArtifact: {out_path}")
    print(f"Wrote Delivery Output: {delivery_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
