"""Define normalized hook payload models."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_hooks.enums import HookEventName, HookProvider
from agent_hooks.models.schemas.json_types import JsonObject


@dataclass(frozen=True)
class ToolInput:
    """Store normalized tool input values for display decisions."""

    raw: JsonObject = field(default_factory=dict)
    command: str = ""
    file_path: str = ""
    description: str = ""
    url: str = ""
    query: str = ""
    prompt: str = ""
    pattern: str = ""


@dataclass(frozen=True)
class HookPayload:
    """Store the normalized hook payload used by processing logic."""

    raw: JsonObject = field(default_factory=dict)
    provider: HookProvider = HookProvider.CLAUDE_CODE
    event_name: HookEventName = HookEventName.UNKNOWN
    raw_event_name: str = ""
    raw_notification_type: str = ""
    model: str = ""
    permission_mode: str = ""
    title: str = ""
    message: str = ""
    prompt: str = ""
    source: str = ""
    last_assistant_message: str = ""
    error_details: str = ""
    error: str = ""
    session_id: str = ""
    cwd: str = ""
    transcript_path: str = ""
    tool_name: str = ""
    tool_use_id: str = ""
    tool_input: ToolInput = field(default_factory=ToolInput)


@dataclass(frozen=True)
class HookInput:
    """Store the raw stdin payload and parse outcome."""

    raw_input: str
    payload: HookPayload
    parse_error: str | None = None


__all__ = ["HookInput", "HookPayload", "ToolInput"]
