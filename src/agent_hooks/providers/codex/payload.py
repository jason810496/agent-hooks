"""Normalize Codex payloads."""

from __future__ import annotations

from agent_hooks.enums import HookEventName, HookProvider
from agent_hooks.models import HookPayload, JsonObject, ToolInput
from agent_hooks.providers.common import coerce_bool, coerce_object, coerce_text

RAW_EVENT_TO_NORMALIZED = {
    "SessionStart": HookEventName.SESSION_START,
    "PreToolUse": HookEventName.PERMISSION_REQUEST,
    "PostToolUse": HookEventName.POST_TOOL_USE,
    "UserPromptSubmit": HookEventName.USER_PROMPT_SUBMIT,
    "Stop": HookEventName.STOP,
}


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
        turn_id=coerce_text(raw_payload.get("turn_id")),
        tool_name=coerce_text(raw_payload.get("tool_name")),
        tool_use_id=coerce_text(raw_payload.get("tool_use_id")),
        stop_hook_active=coerce_bool(raw_payload.get("stop_hook_active")),
        tool_response=raw_payload.get("tool_response"),
        tool_input=ToolInput(
            raw=tool_input_raw,
            command=coerce_text(tool_input_raw.get("command")),
            prompt=prompt,
        ),
    )
