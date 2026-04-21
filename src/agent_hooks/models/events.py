"""Typed event models exposed to routed hook handlers."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_hooks.enums import HookEventName, HookProvider
from agent_hooks.models.schemas.hooks import ToolInput
from agent_hooks.models.schemas.json_types import JsonObject


@dataclass(frozen=True)
class HookEvent:
    """Represent the common fields exposed to all routed hook handlers."""

    raw: JsonObject = field(default_factory=dict)
    provider: HookProvider = HookProvider.CLAUDE_CODE
    event_name: HookEventName = HookEventName.UNKNOWN
    raw_event_name: str = ""
    model: str = ""
    session_id: str = ""
    cwd: str = ""
    transcript_path: str = ""


@dataclass(frozen=True)
class NotificationEvent(HookEvent):
    """Represent the schema injected into ``@app.notification()`` handlers."""

    raw_notification_type: str = ""
    title: str = ""
    message: str = ""


@dataclass(frozen=True)
class PermissionRequestEvent(HookEvent):
    """Represent the schema injected into ``@app.permission()`` handlers."""

    permission_mode: str = ""
    prompt: str = ""
    source: str = ""
    tool_name: str = ""
    tool_use_id: str = ""
    tool_input: ToolInput = field(default_factory=ToolInput)


@dataclass(frozen=True)
class SessionStartEvent(HookEvent):
    """Represent the schema injected into ``@app.session_start()`` handlers."""

    permission_mode: str = ""


@dataclass(frozen=True)
class UserPromptSubmitEvent(HookEvent):
    """Represent the schema injected into ``@app.user_prompt_submit()`` handlers."""

    prompt: str = ""
    source: str = ""
    last_assistant_message: str = ""


@dataclass(frozen=True)
class PostToolUseEvent(HookEvent):
    """Represent the schema injected into ``@app.post_tool_use()`` handlers."""

    tool_name: str = ""
    tool_use_id: str = ""
    tool_input: ToolInput = field(default_factory=ToolInput)
    last_assistant_message: str = ""


@dataclass(frozen=True)
class StopEvent(HookEvent):
    """Represent the schema injected into ``@app.stop()`` handlers."""

    last_assistant_message: str = ""


@dataclass(frozen=True)
class StopFailureEvent(StopEvent):
    """Represent the schema injected into ``@app.stop_failure()`` handlers."""

    error_details: str = ""
    error: str = ""


__all__ = [
    "HookEvent",
    "NotificationEvent",
    "PermissionRequestEvent",
    "PostToolUseEvent",
    "SessionStartEvent",
    "StopEvent",
    "StopFailureEvent",
    "UserPromptSubmitEvent",
]
