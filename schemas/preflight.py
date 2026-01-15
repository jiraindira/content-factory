from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Literal


class QAIssue(BaseModel):
    rule_id: str = Field(..., description="Stable machine-readable rule identifier.")
    level: Literal["error", "warning"] = Field(..., description="Severity level.")
    message: str = Field(..., description="Human-readable message.")
    meta: dict[str, Any] = Field(default_factory=dict, description="Optional structured context.")


class PreflightQAReport(BaseModel):
    ok: bool = Field(..., description="True if the post passed preflight QA checks.")
    strict: bool = Field(..., description="Whether strict mode was enabled (fail blocks publishing).")

    # Human-readable summaries (kept for convenience)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    # Machine-readable issues
    issues: list[QAIssue] = Field(default_factory=list)

    metrics: dict[str, int] = Field(default_factory=dict, description="Useful counts (placeholders, picks, etc).")

    mode: Literal["block", "warn_only"] = Field(..., description="Outcome mode for publishing decision.")
