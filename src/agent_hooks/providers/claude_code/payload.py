"""Normalize and detect Claude Code payloads."""

from __future__ import annotations

from agent_hooks.enums import HookEventName, HookProvider
from agent_hooks.models.schemas.hooks import HookPayload, ToolInput
from agent_hooks.models.schemas.json_types import JsonObject
from agent_hooks.providers.common import coerce_object, coerce_text

RAW_EVENT_TO_NORMALIZED = {
    "Notification": HookEventName.NOTIFICATION,
    "PermissionRequest": HookEventName.PERMISSION_REQUEST,
    "Stop": HookEventName.STOP,
    "StopFailure": HookEventName.STOP_FAILURE,
}
ASK_USER_QUESTION_TOOL_NAME = "AskUserQuestion"
CLAUDE_ONLY_EVENTS = frozenset(
    {
        "Notification",
        "PermissionRequest",
        "PermissionDenied",
        "StopFailure",
        "InstructionsLoaded",
        "SubagentStart",
        "SubagentStop",
        "TaskCreated",
        "TaskCompleted",
        "TeammateIdle",
        "ConfigChange",
        "CwdChanged",
        "FileChanged",
        "WorktreeCreate",
        "WorktreeRemove",
        "PreCompact",
        "PostCompact",
        "Elicitation",
        "ElicitationResult",
        "SessionEnd",
    }
)
CODEX_MARKERS = {"session_id", "cwd", "permission_mode", "transcript_path"}


def matches_payload(raw_payload: JsonObject) -> bool:
    """Return whether the raw payload should be handled by Claude Code."""
    raw_event_name = coerce_text(raw_payload.get("hook_event_name"))
    if raw_event_name in CLAUDE_ONLY_EVENTS:
        return True
    if raw_event_name == "SessionStart":
        return not any(marker in raw_payload for marker in CODEX_MARKERS)
    if raw_event_name == "PreToolUse":
        if "turn_id" in raw_payload:
            return False
        return coerce_text(raw_payload.get("tool_name")) == ASK_USER_QUESTION_TOOL_NAME
    if raw_event_name in {"PostToolUse", "UserPromptSubmit"}:
        return False
    if raw_event_name == "Stop":
        return "turn_id" not in raw_payload
    return False


def build_hook_payload(raw_payload: JsonObject) -> HookPayload:
    """Normalize a Claude Code payload into the shared model."""
    raw_event_name = coerce_text(raw_payload.get("hook_event_name"))
    raw_notification_type = coerce_text(raw_payload.get("notification_type"))
    tool_input_raw = coerce_object(raw_payload.get("tool_input"))
    tool_name = coerce_text(raw_payload.get("tool_name"))

    event_name = RAW_EVENT_TO_NORMALIZED.get(raw_event_name, HookEventName.UNKNOWN)
    if raw_event_name == "PreToolUse" and tool_name == ASK_USER_QUESTION_TOOL_NAME:
        event_name = HookEventName.PERMISSION_REQUEST

    return HookPayload(
        raw=dict(raw_payload),
        provider=HookProvider.CLAUDE_CODE,
        event_name=event_name,
        raw_event_name=raw_event_name,
        raw_notification_type=raw_notification_type,
        model=coerce_text(raw_payload.get("model")),
        permission_mode=coerce_text(raw_payload.get("permission_mode")),
        title=coerce_text(raw_payload.get("title")),
        message=coerce_text(raw_payload.get("message")),
        prompt=coerce_text(raw_payload.get("prompt")),
        source=coerce_text(raw_payload.get("source")),
        last_assistant_message=coerce_text(raw_payload.get("last_assistant_message")),
        error_details=coerce_text(raw_payload.get("error_details")),
        error=coerce_text(raw_payload.get("error")),
        session_id=coerce_text(raw_payload.get("session_id")),
        cwd=coerce_text(raw_payload.get("cwd")),
        transcript_path=coerce_text(raw_payload.get("transcript_path")),
        tool_name=tool_name,
        tool_use_id=coerce_text(raw_payload.get("tool_use_id")),
        tool_input=ToolInput(
            raw=tool_input_raw,
            command=coerce_text(tool_input_raw.get("command")),
            file_path=coerce_text(tool_input_raw.get("file_path")),
            description=coerce_text(tool_input_raw.get("description")),
            url=coerce_text(tool_input_raw.get("url")),
            query=coerce_text(tool_input_raw.get("query")),
            prompt=coerce_text(tool_input_raw.get("prompt")),
            pattern=coerce_text(tool_input_raw.get("pattern")),
        ),
    )
