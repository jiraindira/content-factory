from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from agents.image_generation_agent import ImageGenerationAgent  # noqa: E402


@dataclass
class _NullLLM:
    def complete_json(self, *, system: str, user: str) -> dict:  # pragma: no cover
        raise RuntimeError("LLM should not be used when regenerating variants from source")


@dataclass
class _NullImageGen:
    def generate(self, *, prompt: str, fmt: str, width: int, height: int) -> bytes:  # pragma: no cover
        raise RuntimeError("Image generation should not be used when regenerating variants from source")


def _iter_post_dirs(posts_dir: Path) -> list[Path]:
    if not posts_dir.exists():
        return []
    return sorted([p for p in posts_dir.iterdir() if p.is_dir()], key=lambda p: p.name)


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Regenerate hero variants (hero.webp / hero_home.webp / hero_card.webp) from hero_source.webp "
            "using the current variant dimensions. No OpenAI calls are made."
        )
    )
    p.add_argument("--posts-dir", default="site/public/images/posts")
    p.add_argument("--slug", default=None, help="Only regenerate for this slug")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    posts_dir = Path(args.posts_dir)
    targets: list[Path]

    if args.slug:
        targets = [posts_dir / str(args.slug)]
    else:
        targets = _iter_post_dirs(posts_dir)

    agent = ImageGenerationAgent(
        llm=_NullLLM(),
        image_gen=_NullImageGen(),
        public_images_dir=str(posts_dir.parent),
        posts_subdir=posts_dir.name,
    )

    updated = 0
    skipped_no_source = 0
    missing_dir = 0

    for post_dir in targets:
        if not post_dir.exists() or not post_dir.is_dir():
            missing_dir += 1
            continue

        slug = post_dir.name
        source = post_dir / "hero_source.webp"
        if not source.exists() or source.stat().st_size == 0:
            skipped_no_source += 1
            print(f"⏭️  {slug}: missing hero_source.webp (skipping)")
            continue

        if args.dry_run:
            print(f"🧪 {slug}: would regenerate variants from hero_source.webp")
            continue

        agent.ensure_variants_from_source(source, post_dir)
        updated += 1
        print(f"✅ {slug}: variants regenerated/validated")

    print(
        "\nSummary:\n"
        f"- processed: {len(targets)}\n"
        f"- updated: {updated}\n"
        f"- skipped (no source): {skipped_no_source}\n"
        f"- missing dir: {missing_dir}\n"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
