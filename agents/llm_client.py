from __future__ import annotations

import os
from typing import Dict, List, Optional

from openai import OpenAI
from lib.env import load_env
load_env()


DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")
DEFAULT_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
DEFAULT_SEED = int(os.getenv("OPENAI_SEED", "1337"))


class LLMClient:
    """
    Thin wrapper around OpenAI text generation (Responses API).

    Compatibility handling:
      - Some SDK versions don't accept seed=.
      - Some models/endpoints don't accept temperature=.
    We try with optional params first, then gracefully retry without them.
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.client = OpenAI()
        self.model = model

    def generate_text(
        self,
        *,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = DEFAULT_TEMPERATURE,
        seed: Optional[int] = DEFAULT_SEED,
        max_output_tokens: Optional[int] = None,
        reasoning_effort: str = "low",
    ) -> str:
        base_kwargs: dict = {
            "model": self.model,
            "input": messages,
            "reasoning": {"effort": reasoning_effort},
        }
        if max_output_tokens is not None:
            base_kwargs["max_output_tokens"] = int(max_output_tokens)

        # We'll progressively drop unsupported params.
        attempt_kwargs = dict(base_kwargs)

        if temperature is not None:
            attempt_kwargs["temperature"] = float(temperature)

        # Try including seed if provided
        if seed is not None:
            try:
                resp = self.client.responses.create(**attempt_kwargs, seed=int(seed))
                return (resp.output_text or "").strip()
            except TypeError as e:
                # seed not accepted by this SDK version
                msg = str(e).lower()
                if "unexpected keyword argument" not in msg or "seed" not in msg:
                    raise
            except Exception as e:
                # model may reject temperature or other params; fall through to retry logic below
                pass

        # Try without seed
        try:
            resp = self.client.responses.create(**attempt_kwargs)
            return (resp.output_text or "").strip()
        except Exception as e:
            # If the model rejects temperature, retry without temperature
            msg = str(e).lower()
            if "unsupported parameter" in msg and "temperature" in msg:
                attempt_kwargs.pop("temperature", None)
                resp = self.client.responses.create(**attempt_kwargs)
                return (resp.output_text or "").strip()
            raise
