"""Define processing-layer result models."""

from __future__ import annotations

from dataclasses import dataclass

from agent_hooks.models.schemas.display import AppleScriptResult, DisplaySpec
from agent_hooks.models.schemas.responses import HookResponseProtocol


@dataclass(frozen=True)
class HookProcessingResult:
    """Store the processing result before logging and emission."""

    display: DisplaySpec | None
    transport_result: AppleScriptResult | None
    response: HookResponseProtocol
    error: str | None = None


__all__ = ["HookProcessingResult"]
