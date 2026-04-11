"""Claude Code provider adapter."""

from __future__ import annotations

from agent_hooks.enums import HookEventName, HookProvider, NotificationType
from agent_hooks.models import (
    HookPayload,
    JsonObject,
    PermissionRule,
    PermissionSuggestion,
    ToolInput,
)
from agent_hooks.providers.common import coerce_enum, coerce_object, coerce_object_list, coerce_text

RAW_EVENT_TO_NORMALIZED = {
    "Notification": HookEventName.NOTIFICATION,
    "PermissionRequest": HookEventName.PERMISSION_REQUEST,
    "Stop": HookEventName.STOP,
    "StopFailure": HookEventName.STOP_FAILURE,
}

NORMALIZED_EVENT_TO_WIRE = {
    HookEventName.NOTIFICATION: "Notification",
    HookEventName.PERMISSION_REQUEST: "PermissionRequest",
    HookEventName.STOP: "Stop",
    HookEventName.STOP_FAILURE: "StopFailure",
}


def build_hook_payload(raw_payload: JsonObject) -> HookPayload:
    """Normalize a Claude Code payload into the shared model."""
    raw_event_name = coerce_text(raw_payload.get("hook_event_name"))
    raw_notification_type = coerce_text(raw_payload.get("notification_type"))
    tool_input_raw = coerce_object(raw_payload.get("tool_input"))

    return HookPayload(
        raw=dict(raw_payload),
        provider=HookProvider.CLAUDE_CODE,
        event_name=RAW_EVENT_TO_NORMALIZED.get(raw_event_name, HookEventName.UNKNOWN),
        raw_event_name=raw_event_name,
        notification_type=coerce_enum(
            raw_notification_type,
            NotificationType,
            NotificationType.UNKNOWN,
        ),
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
        tool_name=coerce_text(raw_payload.get("tool_name")),
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
        permission_suggestions=tuple(build_permission_suggestions(raw_payload)),
    )


def build_permission_suggestions(raw_payload: JsonObject) -> list[PermissionSuggestion]:
    """Normalize Claude permission suggestions from the raw payload."""
    suggestions: list[PermissionSuggestion] = []
    for suggestion_raw in coerce_object_list(raw_payload.get("permission_suggestions")):
        rules = tuple(build_permission_rules(suggestion_raw))
        suggestions.append(PermissionSuggestion(raw=dict(suggestion_raw), rules=rules))
    return suggestions


def build_permission_rules(suggestion_raw: JsonObject) -> list[PermissionRule]:
    """Normalize Claude permission rules from one suggestion payload."""
    rules: list[PermissionRule] = []
    for rule_raw in coerce_object_list(suggestion_raw.get("rules")):
        rules.append(
            PermissionRule(
                tool_name=coerce_text(rule_raw.get("toolName")),
                rule_content=coerce_text(rule_raw.get("ruleContent")),
                raw=dict(rule_raw),
            )
        )
    return rules


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
    event_name = RAW_EVENT_TO_NORMALIZED.get(normalized_event_name)
    if event_name is None:
        try:
            event_name = HookEventName(normalized_event_name)
        except ValueError:
            return {}

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
