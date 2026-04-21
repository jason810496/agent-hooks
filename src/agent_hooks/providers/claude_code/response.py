"""Render Claude Code hook responses."""

from __future__ import annotations

import contextlib

from agent_hooks.enums import HookEventName
from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.models.schemas.json_types import JsonObject
from agent_hooks.providers.claude_code.payload import RAW_EVENT_TO_NORMALIZED
from agent_hooks.providers.common import coerce_object, coerce_text

NORMALIZED_EVENT_TO_WIRE = {
    HookEventName.NOTIFICATION: "Notification",
    HookEventName.PERMISSION_REQUEST: "PermissionRequest",
    HookEventName.STOP: "Stop",
    HookEventName.STOP_FAILURE: "StopFailure",
}


def render_response_payload(
    raw_payload: JsonObject,
    *,
    input_payload: HookPayload | None = None,
) -> JsonObject:
    """Render a provider-neutral response payload into Claude's wire format."""
    payload: JsonObject = {"suppressOutput": bool(raw_payload.get("suppressOutput", True))}
    if "continue" in raw_payload:
        payload["continue"] = bool(raw_payload.get("continue"))
    if raw_payload.get("stopReason"):
        payload["stopReason"] = coerce_text(raw_payload.get("stopReason"))
    if raw_payload.get("systemMessage"):
        payload["systemMessage"] = coerce_text(raw_payload.get("systemMessage"))
    if raw_payload.get("decision"):
        payload["decision"] = coerce_text(raw_payload.get("decision"))
    if raw_payload.get("reason"):
        payload["reason"] = coerce_text(raw_payload.get("reason"))
    hook_specific_output = render_hook_specific_output(
        coerce_object(raw_payload.get("hookSpecificOutput")),
        input_payload=input_payload,
    )
    if hook_specific_output:
        payload["hookSpecificOutput"] = hook_specific_output
    return payload


def render_hook_specific_output(
    raw_payload: JsonObject,
    *,
    input_payload: HookPayload | None = None,
) -> JsonObject:
    """Render the hook-specific output block for Claude Code."""
    if not raw_payload:
        return {}

    normalized_event_name = coerce_text(raw_payload.get("hookEventName"))
    event_name = RAW_EVENT_TO_NORMALIZED.get(normalized_event_name, HookEventName.UNKNOWN)
    if event_name == HookEventName.UNKNOWN:
        with contextlib.suppress(ValueError):
            event_name = HookEventName(normalized_event_name)

    wire_event_name = (
        input_payload.raw_event_name
        if input_payload is not None and input_payload.raw_event_name
        else NORMALIZED_EVENT_TO_WIRE.get(event_name)
    )
    if wire_event_name is None:
        return {}

    payload: JsonObject = {"hookEventName": wire_event_name}
    decision = coerce_object(raw_payload.get("decision"))
    if wire_event_name == "PermissionRequest" and decision:
        payload["decision"] = decision
        return payload

    if wire_event_name == "PreToolUse":
        behavior = coerce_text(decision.get("behavior"))
        if behavior:
            payload["permissionDecision"] = behavior
        if raw_payload.get("permissionDecisionReason"):
            payload["permissionDecisionReason"] = coerce_text(
                raw_payload.get("permissionDecisionReason")
            )
        if raw_payload.get("updatedInput") is not None:
            payload["updatedInput"] = raw_payload.get("updatedInput")
        if raw_payload.get("additionalContext"):
            payload["additionalContext"] = coerce_text(raw_payload.get("additionalContext"))
        return payload if len(payload) > 1 else {}

    if raw_payload.get("additionalContext"):
        payload["additionalContext"] = coerce_text(raw_payload.get("additionalContext"))
    return payload
