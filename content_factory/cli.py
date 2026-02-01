from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from content_factory.adapters.dispatch import render_for_request, write_delivery
from content_factory.artifact_io import write_content_artifact
from content_factory.artifact_validation import validate_artifact_against_specs
from content_factory.brand_context import (
    artifact_path_for_brand,
    build_brand_context_artifact,
    write_brand_context_artifact,
)
from content_factory.compiler import compile_content_artifact
from content_factory.onboarding import write_onboarding_files
from content_factory.validation import load_brand_profile, load_content_request, validate_request_against_brand


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _abs_from_repo(repo_root: Path, p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (repo_root / path)


def cmd_onboard(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    publish_date = date.fromisoformat(args.publish_date) if args.publish_date else date.today()

    paths = write_onboarding_files(
        repo_root=repo_root,
        brand_id=args.brand_id,
        domains_supported=args.domains_supported.split(","),
        domain_primary=args.domain_primary,
        publish_date=publish_date,
    )

    print(f"Wrote brand: {paths.brand_path}")
    print(f"Wrote request: {paths.request_path}")
    print("Next: edit the allowlist, policies, and sources; then validate.")
    return 0


def cmd_validate_brand(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    brand_path = _abs_from_repo(repo_root, args.brand)
    _ = load_brand_profile(brand_path)
    print(f"OK: brand file valid: {brand_path}")
    return 0


def cmd_validate_request(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    brand_path = _abs_from_repo(repo_root, args.brand)
    request_path = _abs_from_repo(repo_root, args.request)

    brand = load_brand_profile(brand_path)
    req = load_content_request(request_path)
    validate_request_against_brand(brand=brand, request=req)
    print(f"OK: request valid against brand: {request_path}")
    return 0


def cmd_build_context(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    brand_path = _abs_from_repo(repo_root, args.brand)
    brand = load_brand_profile(brand_path)

    artifact = build_brand_context_artifact(brand=brand, repo_root=repo_root)
    out_path = write_brand_context_artifact(repo_root=repo_root, artifact=artifact)
    print(f"Wrote BrandContextArtifact: {out_path}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    brand_path = _abs_from_repo(repo_root, args.brand)
    request_path = _abs_from_repo(repo_root, args.request)

    brand = load_brand_profile(brand_path)
    req = load_content_request(request_path)
    validate_request_against_brand(brand=brand, request=req)

    ctx_path = artifact_path_for_brand(repo_root=repo_root, brand_id=brand.brand_id)
    if not ctx_path.exists() and args.build_context_if_missing:
        artifact = build_brand_context_artifact(brand=brand, repo_root=repo_root)
        ctx_path = write_brand_context_artifact(repo_root=repo_root, artifact=artifact)

    if not ctx_path.exists():
        raise FileNotFoundError(
            f"BrandContextArtifact not found: {ctx_path}. Run `content-factory build-context --brand ...` first."
        )

    from content_factory.brand_context import BrandContextArtifact

    ctx = BrandContextArtifact.model_validate_json(ctx_path.read_text(encoding="utf-8"))

    run_id = args.run_id or request_path.stem
    artifact = compile_content_artifact(brand=brand, request=req, brand_context=ctx, run_id=run_id)
    validate_artifact_against_specs(brand=brand, request=req, artifact=artifact)

    out_artifact_path = write_content_artifact(repo_root=repo_root, artifact=artifact)

    delivery = render_for_request(brand=brand, request=req, artifact=artifact)
    out_delivery_path = write_delivery(repo_root=repo_root, delivery=delivery)

    print(f"Wrote ContentArtifact: {out_artifact_path}")
    print(f"Wrote Delivery Output: {out_delivery_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="content-factory", description="AI Content Factory CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    onboard = sub.add_parser("onboard", help="Scaffold brand + request YAML for a new client")
    onboard.add_argument("--brand-id", required=True)
    onboard.add_argument("--domains-supported", required=True, help="Comma-separated domains (e.g. leadership,tech)")
    onboard.add_argument("--domain-primary", required=True)
    onboard.add_argument("--publish-date", required=False, help="YYYY-MM-DD (defaults to today)")
    onboard.set_defaults(func=cmd_onboard)

    vb = sub.add_parser("validate-brand", help="Validate a brand YAML")
    vb.add_argument("--brand", required=True)
    vb.set_defaults(func=cmd_validate_brand)

    vr = sub.add_parser("validate-request", help="Validate a request YAML against a brand")
    vr.add_argument("--brand", required=True)
    vr.add_argument("--request", required=True)
    vr.set_defaults(func=cmd_validate_request)

    bc = sub.add_parser("build-context", help="Build BrandContextArtifact JSON (robots enforced)")
    bc.add_argument("--brand", required=True)
    bc.set_defaults(func=cmd_build_context)

    run = sub.add_parser("run", help="Compile a ContentArtifact + delivery output")
    run.add_argument("--brand", required=True)
    run.add_argument("--request", required=True)
    run.add_argument("--run-id", required=False)
    run.add_argument(
        "--build-context-if-missing",
        action="store_true",
        help="If BrandContextArtifact is missing, build it first.",
    )
    run.set_defaults(func=cmd_run)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
