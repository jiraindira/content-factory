from __future__ import annotations

import os
from pathlib import Path

def load_env() -> None:
    """
    Load .env into process environment if python-dotenv is installed.
    Safe no-op if not installed or .env missing.
    """
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return

    # Prefer repo-root .env
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        return

    # Fallback: common pattern ".env/.env"
    alt = Path(".env") / ".env"
    if alt.exists():
        load_dotenv(dotenv_path=alt)
