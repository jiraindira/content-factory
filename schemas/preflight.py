from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


class PreflightQAReport(BaseModel):
    ok: bool = Field(..., description="True if the post passed preflight QA checks.")
    strict: bool = Field(..., description="Whether strict mode was enabled (fail blocks publishing).")

    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    metrics: dict[str, int] = Field(default_factory=dict, description="Useful counts (placeholders, picks, etc).")

    mode: Literal["block", "warn_only"] = Field(..., description="Outcome mode for publishing decision.")
