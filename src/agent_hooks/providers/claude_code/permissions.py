"""Build Claude Code permission dialogs and responses."""

from __future__ import annotations

from dataclasses import dataclass

from agent_hooks.enums import DialogButton, HookEventName, PermissionBehavior, PermissionDestination
from agent_hooks.models import (
    AppleScriptDialogResponse,
    HookPayload,
    HookSpecificOutput,
    JsonObject,
    PermissionDecision,
    PermissionUpdate,
)
from agent_hooks.providers.common import coerce_object_list, coerce_text


@dataclass(frozen=True)
class PermissionRule:
    """Store one Claude permission rule."""

    tool_name: str = ""
    rule_content: str = ""
    raw: JsonObject | None = None


@dataclass(frozen=True)
class PermissionSuggestion:
    """Store one Claude permission suggestion."""

    raw: JsonObject
    rules: tuple[PermissionRule, ...] = ()


def build_permission_response(
    button: DialogButton,
    payload: HookPayload,
) -> AppleScriptDialogResponse:
    """Build the Claude permission response for one dialog decision."""
    decision = _build_permission_decision(button, payload)
    return AppleScriptDialogResponse(
        button=button,
        payload=payload,
        hook_specific_output=HookSpecificOutput(
            hook_event_name=HookEventName.PERMISSION_REQUEST,
            decision=decision,
            permission_decision_reason=(
                "Permission denied by local user." if button == DialogButton.DENY else ""
            ),
        ),
    )


def build_permission_suggestions(raw_payload: JsonObject) -> tuple[PermissionSuggestion, ...]:
    """Normalize Claude permission suggestions from the raw payload."""
    suggestions: list[PermissionSuggestion] = []
    for suggestion_raw in coerce_object_list(raw_payload.get("permission_suggestions")):
        suggestions.append(
            PermissionSuggestion(
                raw=dict(suggestion_raw),
                rules=tuple(build_permission_rules(suggestion_raw)),
            )
        )
    return tuple(suggestions)


def build_permission_rules(suggestion_raw: JsonObject) -> tuple[PermissionRule, ...]:
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
    return tuple(rules)


def first_permission_rule(payload: HookPayload) -> PermissionRule | None:
    """Return the first available Claude permission rule preview."""
    suggestions = build_permission_suggestions(payload.raw)
    if not suggestions:
        return None
    first_suggestion = suggestions[0]
    if not first_suggestion.rules:
        return None
    return first_suggestion.rules[0]


def _build_permission_decision(
    button: DialogButton,
    payload: HookPayload,
) -> PermissionDecision:
    """Build the Claude permission decision for one dialog button."""
    if button == DialogButton.DENY:
        return PermissionDecision(behavior=PermissionBehavior.DENY)

    updates: tuple[PermissionUpdate, ...] = ()
    if button == DialogButton.ALWAYS_ALLOW:
        updates = tuple(
            PermissionUpdate(
                source=suggestion.raw,
                destination=PermissionDestination.SESSION,
            )
            for suggestion in build_permission_suggestions(payload.raw)
        )
    return PermissionDecision(
        behavior=PermissionBehavior.ALLOW,
        updated_permissions=updates,
    )
