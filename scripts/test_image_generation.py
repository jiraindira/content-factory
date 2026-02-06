from __future__ import annotations

import argparse
import json
import os
import shutil
import importlib
import sys
import time
from pathlib import Path

# Ensure repository root is on sys.path so imports like `lib.*` resolve when
# running this file as `python scripts/test_image_generation.py`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.env import load_env


def _require_env(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if not v:
        raise SystemExit(
            f"Missing {name}. Set it in your environment (or .env) before running this script."
        )
    return v


def _readable_size(n: int) -> str:
    size = float(n)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{size:.0f}B" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}GB"


def _verify_image(path: Path) -> tuple[int, int, str]:
    try:
        Image = importlib.import_module("PIL.Image")  # type: ignore[assignment]
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Pillow is required to verify image dimensions/format. Install `pillow` or skip verification."
        ) from e

    with Image.open(path) as im:  # type: ignore[attr-defined]
        w, h = im.size
        fmt = (im.format or "").lower()
        return w, h, fmt


def run_direct(*, prompt: str, out_path: Path) -> int:
    from integrations.openai_adapters import OpenAIImageGenerator

    _require_env("OPENAI_API_KEY")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    gen = OpenAIImageGenerator()
    data = gen.generate(prompt=prompt, fmt="webp", width=2000, height=1125)
    out_path.write_bytes(data)

    try:
        w, h, fmt = _verify_image(out_path)
    except Exception as e:
        print(f"⚠️ Generated file but could not verify dimensions: {e}")
        w = h = 0
        fmt = "(unknown)"
    print("✅ Direct image generation OK")
    print(f"- file: {out_path}")
    print(f"- size: {_readable_size(out_path.stat().st_size)}")
    print(f"- format: {fmt}")
    if w and h:
        print(f"- dimensions: {w}x{h}")
    return 0


def run_agent(
    *,
    slug: str,
    category: str | None,
    title: str,
    intro: str,
    picks: list[str],
    style_id: str | None,
    force: bool,
) -> int:
    from agents.image_generation_agent import ImageGenerationAgent
    from integrations.openai_adapters import OpenAIImageGenerator, OpenAIJsonLLM
    from schemas.hero_image import HeroImageRequest

    _require_env("OPENAI_API_KEY")

    public_images_dir = Path("site/public/images")
    post_dir = public_images_dir / "posts" / slug

    backup_dir: Path | None = None

    if force:
        if post_dir.exists():
            ts = time.strftime("%Y%m%d_%H%M%S")
            backup_dir = post_dir.with_name(f"{post_dir.name}__backup_{ts}")
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)
            shutil.move(str(post_dir), str(backup_dir))

    agent = ImageGenerationAgent(
        llm=OpenAIJsonLLM(),
        image_gen=OpenAIImageGenerator(),
        public_images_dir=str(public_images_dir),
        posts_subdir="posts",
    )

    req = HeroImageRequest(
        slug=slug,
        category=category,
        title=title,
        style_id=style_id,
        intro=intro,
        picks=picks,
        alternatives=None,
    )

    try:
        out = agent.run(req)
    except Exception:
        # Restore previous folder to avoid accidental data loss when the model/API fails.
        if backup_dir is not None and backup_dir.exists():
            shutil.rmtree(post_dir, ignore_errors=True)
            shutil.move(str(backup_dir), str(post_dir))
        raise

    # If generation succeeded, keep the backup folder only when explicitly desired.
    # Default: remove it to avoid clutter.
    if backup_dir is not None and backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)

    # Verify output files exist on disk
    public_root = Path("site/public")
    disk_paths = {
        "hero": public_root / out.hero_image_path.lstrip("/"),
        "hero_home": public_root / (out.hero_image_home_path or "").lstrip("/") if out.hero_image_home_path else None,
        "hero_card": public_root / (out.hero_image_card_path or "").lstrip("/") if out.hero_image_card_path else None,
        "hero_source": public_root / (out.hero_source_path or "").lstrip("/") if out.hero_source_path else None,
    }

    print("✅ Agent hero generation returned:")
    print(json.dumps(out.model_dump(), indent=2))

    for k, p in disk_paths.items():
        if p is None:
            continue
        if not p.exists() or p.stat().st_size == 0:
            raise SystemExit(f"❌ Missing or empty output file: {k} -> {p}")
        try:
            w, h, fmt = _verify_image(p)
            dims = f" {w}x{h}" if w and h else ""
            print(f"- {k}: {p} ({_readable_size(p.stat().st_size)}) {fmt}{dims}")
        except Exception:
            print(f"- {k}: {p} ({_readable_size(p.stat().st_size)})")

    # Optional: compare against placeholder to detect backfill
    placeholder = public_images_dir / "placeholder-hero.webp"
    hero = disk_paths["hero"]
    if placeholder.exists() and hero and hero.exists():
        try:
            if placeholder.read_bytes() == hero.read_bytes():
                print("⚠️ hero.webp matches placeholder-hero.webp (likely placeholder backfill)")
        except Exception:
            pass

    return 0


def main() -> int:
    load_env()

    p = argparse.ArgumentParser(description="Test OpenAI image generation in isolation")
    p.add_argument("--mode", choices=["direct", "agent"], default="agent")
    p.add_argument("--slug", default="_image_test")
    p.add_argument("--category", default="travel")
    p.add_argument("--title", default="Travel rain gear essentials")
    p.add_argument(
        "--intro",
        default=(
            "A short, practical guide for UK travellers on what to pack for wet weather. "
            "Keep it UK-general and avoid city-specific framing."
        ),
    )
    p.add_argument(
        "--picks",
        default="Windproof umbrella; Lightweight poncho; Packable waterproof jacket",
        help="Semicolon-separated pick snippets",
    )
    p.add_argument(
        "--style-id",
        default=None,
        help="Optional style override (e.g. 'category_illustration_v1')",
    )
    p.add_argument(
        "--prompt",
        default=(
            "Minimal editorial illustration, clean shapes, generous white space. "
            "A cohesive scene representing travel rain gear essentials: an umbrella, a folded poncho, "
            "and a packable rain jacket near a small travel bag. No text, no logos."
        ),
    )
    p.add_argument("--out", default="output/debug_image.webp")
    p.add_argument("--force", action="store_true", help="Delete existing hero folder before generating")

    args = p.parse_args()

    if args.mode == "direct":
        return run_direct(prompt=str(args.prompt), out_path=Path(args.out))

    picks = [s.strip() for s in str(args.picks).split(";") if s.strip()]
    return run_agent(
        slug=str(args.slug),
        category=str(args.category) if args.category else None,
        title=str(args.title),
        intro=str(args.intro),
        picks=picks,
        style_id=str(args.style_id) if args.style_id else None,
        force=bool(args.force),
    )


if __name__ == "__main__":
    raise SystemExit(main())
