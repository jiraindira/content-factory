from __future__ import annotations

import base64
import json
import os
import urllib.request
from typing import Any

from openai import OpenAI


class OpenAIJsonLLM:
    """
    JSON-returning chat adapter.
    Requires OPENAI_API_KEY in env.
    """

    def __init__(self, *, model: str | None = None) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        self._client = OpenAI(api_key=api_key)

        # Configurable without code edits
        self._model = model or os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")

    def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        content = resp.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except Exception:
            return {}


class OpenAIImageGenerator:
    """
    Image generator adapter returning bytes.
    Requires OPENAI_API_KEY in env.

    Important:
    - Some OpenAI SDK variants do not accept `response_format` for images.generate.
    - We handle both possible returns:
        - base64 payload (b64_json / base64-like field)
        - URL payload (download bytes)
    """

    def __init__(self, *, model: str | None = None) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        self._client = OpenAI(api_key=api_key)

        # Configurable without code edits
        self._model = model or os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")

    def generate(self, *, prompt: str, fmt: str, width: int, height: int) -> bytes:
        _ = fmt  # kept for interface stability; OpenAI returns actual image bytes either way

        size = self._size_string(width, height)

        resp = self._client.images.generate(
            model=self._model,
            prompt=prompt,
            size=size,
        )

        if not getattr(resp, "data", None) or not resp.data:
            raise RuntimeError("Image generation response contained no data items.")

        first = resp.data[0]

        # Base64-style output
        b64 = getattr(first, "b64_json", None) or getattr(first, "base64", None)
        if b64:
            return base64.b64decode(b64)

        # URL-style output
        url = getattr(first, "url", None)
        if url:
            with urllib.request.urlopen(url) as r:
                return r.read()

        # Helpful debug detail
        keys = []
        try:
            keys = list(first.__dict__.keys())  # type: ignore[attr-defined]
        except Exception:
            pass

        raise RuntimeError(
            "Image generation response contained neither base64 nor url data. "
            f"Available fields: {keys or '(unknown)'}"
        )

    def _size_string(self, width: int, height: int) -> str:
        if width >= 1400 and height >= 800:
            return "1536x1024"
        if width >= 1024 and height >= 1024:
            return "1024x1024"
        return "1024x1024"
