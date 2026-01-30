from __future__ import annotations

import base64
import json
import os
import urllib.request
from io import BytesIO
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

try:
    # Pillow is optional at import-time, but required for image post-processing.
    from PIL import Image, ImageOps  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore
    ImageOps = None  # type: ignore


class OpenAIJsonLLM:
    """
    JSON-only LLM wrapper with compatibility across openai-python SDK versions.

    We prefer the Responses API. JSON-mode configuration differs across versions:
      - Some versions accept: text={"format": {"type": "json_object"}}
      - Some older versions do not support Responses JSON formatting and require Chat Completions.
    """

    def __init__(self, *, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
        self.client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,  # kept for future JSON schema mode
    ) -> dict[str, Any]:
        # 1) Try Responses API with JSON mode via `text.format`
        text: str | None = None

        try:
            resp = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # ✅ Compatible JSON mode for many SDK versions
                text={"format": {"type": "json_object"}},
            )
            # Newer SDKs expose .output_text
            text = getattr(resp, "output_text", None) or None
        except TypeError:
            # SDK doesn't accept `text=...` or Responses.create signature differs
            text = None

        # 2) Fallback: Chat Completions JSON mode
        if not text:
            try:
                resp2 = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                )
                text = resp2.choices[0].message.content
            except TypeError as e:
                raise RuntimeError(
                    "Your installed openai SDK does not support JSON mode via Responses or Chat Completions. "
                    "Upgrade the `openai` package (recommended), or we can implement a strict JSON parser fallback."
                ) from e

        if not text:
            raise RuntimeError("Model returned empty output; cannot parse JSON.")

        try:
            return json.loads(text)
        except Exception as e:
            raise RuntimeError(f"Model did not return valid JSON. Error={e}. Raw={text[:500]}") from e


class OpenAIImageGenerator:
    """
    Generates an image using OpenAI's image model, returning bytes.

    Adapter matches ImageGenerationAgent's expected interface:
      generate(prompt=..., fmt="webp", width=..., height=...) -> bytes

    It requests a provider-supported size, then deterministically crops/resizes
    to the exact requested dimensions and encodes as webp/png.
    """

    def __init__(self, *, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
        self.client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    def generate(self, *, prompt: str, fmt: str = "webp", width: int, height: int) -> bytes:
        fmt_norm = (fmt or "webp").strip().lower()
        if fmt_norm not in ("webp", "png"):
            raise ValueError(f"Unsupported fmt='{fmt}'. Use 'webp' or 'png'.")

        size_str = self._size_string(width, height)

        resp = self.client.images.generate(
            model=self.model,
            prompt=prompt,
            size=size_str,
        )

        first = resp.data[0]

        # Base64-style output
        b64 = getattr(first, "b64_json", None) or getattr(first, "base64", None)
        if b64:
            raw = base64.b64decode(b64)
            return self._postprocess(raw, width, height, fmt_norm)

        # URL-style output
        url = getattr(first, "url", None)
        if url:
            with urllib.request.urlopen(url) as r:
                raw = r.read()
            return self._postprocess(raw, width, height, fmt_norm)

        keys: list[str] = []
        try:
            keys = list(first.__dict__.keys())  # type: ignore[attr-defined]
        except Exception:
            pass
        raise RuntimeError(f"Image response had neither b64 nor url. Available keys={keys}")

    def _size_string(self, width: int, height: int) -> str:
        """
        Pick a supported provider size closest to the requested aspect.

        Your account supports:
        - 1024x1024
        - 1536x1024 (landscape)
        - 1024x1536 (portrait)
        - auto
        """
        w = max(1, int(width))
        h = max(1, int(height))
        aspect = w / h

        # Landscape
        if aspect >= 1.2:
            return "1536x1024"

        # Portrait
        if aspect <= 0.83:
            return "1024x1536"

        # Square-ish
        return "1024x1024"

    def _postprocess(self, image_bytes: bytes, width: int, height: int, fmt: str) -> bytes:
        if Image is None or ImageOps is None:
            return image_bytes

        target_w = max(1, int(width))
        target_h = max(1, int(height))

        with Image.open(BytesIO(image_bytes)) as im:
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")

            fitted = ImageOps.fit(im, (target_w, target_h), method=Image.LANCZOS, centering=(0.5, 0.5))

            out = BytesIO()
            if fmt == "png":
                fitted.save(out, format="PNG", optimize=True)
                return out.getvalue()

            fitted.save(out, format="WEBP", quality=92, method=6)
            return out.getvalue()
