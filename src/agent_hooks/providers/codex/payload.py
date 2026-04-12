"""Normalize and detect Codex payloads."""

from __future__ import annotations

from agent_hooks.enums import HookEventName, HookProvider
from agent_hooks.models import HookPayload, JsonObject, ToolInput
from agent_hooks.providers.common import coerce_object, coerce_text

RAW_EVENT_TO_NORMALIZED = {
    "SessionStart": HookEventName.SESSION_START,
    "PreToolUse": HookEventName.PERMISSION_REQUEST,
    "PostToolUse": HookEventName.POST_TOOL_USE,
    "UserPromptSubmit": HookEventName.USER_PROMPT_SUBMIT,
    "Stop": HookEventName.STOP,
}


def matches_payload(raw_payload: JsonObject) -> bool:
    """Return whether the raw payload should be handled by Codex."""
    raw_event_name = coerce_text(raw_payload.get("hook_event_name"))
    if raw_event_name in {"PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop"}:
        return "turn_id" in raw_payload
    if raw_event_name == "SessionStart":
        codex_markers = {"session_id", "cwd", "permission_mode", "transcript_path"}
        return any(marker in raw_payload for marker in codex_markers)
    return False


def build_hook_payload(raw_payload: JsonObject) -> HookPayload:
    """Normalize a Codex payload into the shared model."""
    raw_event_name = coerce_text(raw_payload.get("hook_event_name"))
    tool_input_raw = coerce_object(raw_payload.get("tool_input"))
    prompt = coerce_text(raw_payload.get("prompt"))

    return HookPayload(
        raw=dict(raw_payload),
        provider=HookProvider.CODEX,
        event_name=RAW_EVENT_TO_NORMALIZED.get(raw_event_name, HookEventName.UNKNOWN),
        raw_event_name=raw_event_name,
        model=coerce_text(raw_payload.get("model")),
        permission_mode=coerce_text(raw_payload.get("permission_mode")),
        prompt=prompt,
        source=coerce_text(raw_payload.get("source")),
        last_assistant_message=coerce_text(raw_payload.get("last_assistant_message")),
        session_id=coerce_text(raw_payload.get("session_id")),
        cwd=coerce_text(raw_payload.get("cwd")),
        transcript_path=coerce_text(raw_payload.get("transcript_path")),
        tool_name=coerce_text(raw_payload.get("tool_name")),
        tool_use_id=coerce_text(raw_payload.get("tool_use_id")),
        tool_input=ToolInput(
            raw=tool_input_raw,
            command=coerce_text(tool_input_raw.get("command")),
            prompt=prompt,
        ),
    )
