from __future__ import annotations

import base64
import json
import os
import urllib.request
from io import BytesIO
from typing import Any

from openai import OpenAI
from PIL import Image


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

    OpenAI image models support only a limited set of discrete sizes.
    This adapter accepts arbitrary (width,height) and guarantees the returned
    bytes match the requested dimensions by:

      1) Choosing the closest supported OpenAI size by aspect ratio.
      2) Center-cropping to the requested aspect ratio.
      3) Resizing to the exact requested width/height.
      4) Encoding to the requested format.

    Result: the saved hero assets match your CSS containers deterministically.
    """

    def __init__(self, *, model: str | None = None) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        self._client = OpenAI(api_key=api_key)

        # Configurable without code edits
        self._model = model or os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")

    def generate(self, *, prompt: str, fmt: str, width: int, height: int) -> bytes:
        fmt_norm = (fmt or "webp").strip().lower()
        if fmt_norm not in {"webp", "png", "jpg", "jpeg"}:
            fmt_norm = "webp"

        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive integers")

        size = self._choose_openai_size(width, height)

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
            raw = base64.b64decode(b64)
            return self._postprocess(raw, target_w=width, target_h=height, fmt=fmt_norm)

        # URL-style output
        url = getattr(first, "url", None)
        if url:
            with urllib.request.urlopen(url) as r:
                raw = r.read()
            return self._postprocess(raw, target_w=width, target_h=height, fmt=fmt_norm)

        keys: list[str] = []
        try:
            keys = list(first.__dict__.keys())  # type: ignore[attr-defined]
        except Exception:
            pass

        raise RuntimeError(
            "Image generation response contained neither base64 nor url data. "
            f"Available fields: {keys or '(unknown)'}"
        )

    def _choose_openai_size(self, width: int, height: int) -> str:
        """Pick a supported OpenAI size based on requested aspect ratio."""
        ar = width / height

        # Wide
        if ar >= 1.20:
            return "1536x1024"
        # Tall
        if ar <= 0.83:
            return "1024x1536"
        # Square-ish
        return "1024x1024"

    def _postprocess(self, img_bytes: bytes, *, target_w: int, target_h: int, fmt: str) -> bytes:
        with Image.open(BytesIO(img_bytes)) as im:
            im = im.convert("RGB")

            src_w, src_h = im.size
            target_ar = target_w / target_h
            src_ar = src_w / src_h

            # Center-crop to target aspect ratio
            if abs(src_ar - target_ar) > 1e-6:
                if src_ar > target_ar:
                    new_w = int(round(src_h * target_ar))
                    new_h = src_h
                    left = (src_w - new_w) // 2
                    top = 0
                else:
                    new_w = src_w
                    new_h = int(round(src_w / target_ar))
                    left = 0
                    top = (src_h - new_h) // 2

                right = left + new_w
                bottom = top + new_h
                im = im.crop((left, top, right, bottom))

            # Resize to exact target
            im = im.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)

            out = BytesIO()
            if fmt == "png":
                im.save(out, format="PNG", optimize=True)
            elif fmt in {"jpg", "jpeg"}:
                im.save(out, format="JPEG", quality=92, optimize=True, progressive=True)
            else:
                im.save(out, format="WEBP", quality=92, method=6)

            return out.getvalue()
