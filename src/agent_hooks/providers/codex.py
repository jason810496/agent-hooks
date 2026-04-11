"""Codex provider adapter."""

from __future__ import annotations

from agent_hooks.enums import HookEventName, HookProvider
from agent_hooks.models import HookPayload, JsonObject, ToolInput
from agent_hooks.providers.common import (
    coerce_bool,
    coerce_object,
    coerce_text,
)

RAW_EVENT_TO_NORMALIZED = {
    "SessionStart": HookEventName.SESSION_START,
    "PreToolUse": HookEventName.PERMISSION_REQUEST,
    "PostToolUse": HookEventName.POST_TOOL_USE,
    "UserPromptSubmit": HookEventName.USER_PROMPT_SUBMIT,
    "Stop": HookEventName.STOP,
}

NORMALIZED_EVENT_TO_WIRE = {
    HookEventName.SESSION_START: "SessionStart",
    HookEventName.PERMISSION_REQUEST: "PreToolUse",
    HookEventName.POST_TOOL_USE: "PostToolUse",
    HookEventName.USER_PROMPT_SUBMIT: "UserPromptSubmit",
    HookEventName.STOP: "Stop",
}

EVENTS_WITH_CONTINUE = {
    HookEventName.SESSION_START,
    HookEventName.POST_TOOL_USE,
    HookEventName.USER_PROMPT_SUBMIT,
    HookEventName.STOP,
}
EVENTS_WITH_DECISION = {
    HookEventName.PERMISSION_REQUEST,
    HookEventName.POST_TOOL_USE,
    HookEventName.USER_PROMPT_SUBMIT,
    HookEventName.STOP,
}
EVENTS_WITH_HOOK_SPECIFIC_OUTPUT = {
    HookEventName.SESSION_START,
    HookEventName.PERMISSION_REQUEST,
    HookEventName.POST_TOOL_USE,
    HookEventName.USER_PROMPT_SUBMIT,
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


def render_response_payload(
    raw_payload: JsonObject,
    *,
    input_payload: HookPayload | None = None,
) -> JsonObject:
    """Render a provider-neutral response payload into Codex's wire format."""
    payload: JsonObject = {}
    event_name = input_payload.event_name if input_payload is not None else HookEventName.UNKNOWN
    if event_name in EVENTS_WITH_CONTINUE and "continue" in raw_payload:
        payload["continue"] = bool(raw_payload.get("continue"))
    if event_name in EVENTS_WITH_CONTINUE and raw_payload.get("stopReason"):
        payload["stopReason"] = coerce_text(raw_payload.get("stopReason"))
    if raw_payload.get("systemMessage"):
        payload["systemMessage"] = coerce_text(raw_payload.get("systemMessage"))
    if event_name in EVENTS_WITH_DECISION and raw_payload.get("decision"):
        payload["decision"] = coerce_text(raw_payload.get("decision"))
    if event_name in EVENTS_WITH_DECISION and raw_payload.get("reason"):
        payload["reason"] = coerce_text(raw_payload.get("reason"))

    hook_specific_output = (
        render_hook_specific_output(
            coerce_object(raw_payload.get("hookSpecificOutput")),
            event_name=event_name,
        )
        if event_name in EVENTS_WITH_HOOK_SPECIFIC_OUTPUT
        else {}
    )
    if hook_specific_output:
        payload["hookSpecificOutput"] = hook_specific_output
    return payload


def render_hook_specific_output(
    raw_payload: JsonObject,
    *,
    event_name: HookEventName,
) -> JsonObject:
    """Render the hook-specific output block for Codex."""
    if not raw_payload:
        return {}

    normalized_event_name = coerce_text(raw_payload.get("hookEventName"))
    inferred_event_name = RAW_EVENT_TO_NORMALIZED.get(normalized_event_name)
    if inferred_event_name is None:
        try:
            inferred_event_name = HookEventName(normalized_event_name)
        except ValueError:
            inferred_event_name = event_name

    if inferred_event_name != event_name:
        event_name = inferred_event_name

    wire_event_name = NORMALIZED_EVENT_TO_WIRE.get(event_name)
    if wire_event_name is None:
        return {}

    payload: JsonObject = {"hookEventName": wire_event_name}

    if event_name == HookEventName.PERMISSION_REQUEST:
        decision = coerce_object(raw_payload.get("decision"))
        behavior = coerce_text(decision.get("behavior"))
        if raw_payload.get("permissionDecision") and not behavior:
            behavior = coerce_text(raw_payload.get("permissionDecision"))
        if behavior == "deny":
            payload["permissionDecision"] = behavior
        reason = coerce_text(raw_payload.get("permissionDecisionReason"))
        if reason:
            payload["permissionDecisionReason"] = reason

        if set(payload) == {"hookEventName"}:
            return {}
        return payload

    additional_context = coerce_text(raw_payload.get("additionalContext"))
    if additional_context:
        payload["additionalContext"] = additional_context

    if event_name == HookEventName.POST_TOOL_USE:
        return payload

    return payload
