"""Build Claude Code permission dialogs and responses."""

from __future__ import annotations

from dataclasses import dataclass

from agent_hooks.enums import DialogButton, HookEventName, PermissionBehavior, PermissionDestination
from agent_hooks.models.schemas.display import PermissionChoice
from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.models.schemas.json_types import JsonObject, JsonValue
from agent_hooks.models.schemas.permissions import PermissionDecision, PermissionUpdate
from agent_hooks.models.schemas.responses import (
    AppleScriptDialogResponse,
    HookResponse,
    HookSpecificOutput,
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


def build_permission_choice_response(
    payload: HookPayload,
    choice: PermissionChoice | None,
) -> AppleScriptDialogResponse:
    """Build the Claude permission response for one picker selection.

    :param payload: Normalized permission payload.
    :type payload: HookPayload
    :param choice: Selected picker choice, or ``None`` when the picker was dismissed.
    :type choice: PermissionChoice | None
    :return: A deny response when dismissed, an allow-once response for the plain
        allow choice, or an allow response that persists only the chosen suggestion
        as a session rule.
    """
    if choice is None:
        return build_permission_response(DialogButton.DENY, payload)

    if choice.button != DialogButton.ALWAYS_ALLOW or choice.suggestion_index is None:
        return build_permission_response(choice.button, payload)

    suggestions = build_permission_suggestions(payload.raw)
    if not 0 <= choice.suggestion_index < len(suggestions):
        # The picker and the payload disagree on the suggestion set; allow the call
        # without persisting a rule rather than persisting the wrong one.
        return build_permission_response(DialogButton.ALLOW_ONCE, payload)

    selected = suggestions[choice.suggestion_index]
    updates = (
        PermissionUpdate(source=selected.raw, destination=PermissionDestination.SESSION),
    )
    return AppleScriptDialogResponse(
        button=DialogButton.ALWAYS_ALLOW,
        payload=payload,
        hook_specific_output=HookSpecificOutput(
            hook_event_name=HookEventName.PERMISSION_REQUEST,
            decision=PermissionDecision(
                behavior=PermissionBehavior.ALLOW,
                updated_permissions=updates,
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


def describe_permission_rule(rule: PermissionRule) -> str:
    """Return a short human label for one permission rule.

    :param rule: Normalized permission rule.
    :type rule: PermissionRule
    :return: ``ToolName(ruleContent)`` when both are present, the tool name or rule
        content alone when only one is present, or an empty string otherwise.
    """
    tool_name = rule.tool_name.strip()
    rule_content = rule.rule_content.strip()
    if tool_name and rule_content:
        return f"{tool_name}({rule_content})"
    return tool_name or rule_content


def describe_permission_suggestion(suggestion: PermissionSuggestion) -> str:
    """Return a short human label describing what one suggestion would persist.

    :param suggestion: Normalized permission suggestion.
    :type suggestion: PermissionSuggestion
    :return: A joined rule summary, or a label derived from non-rule suggestion
        fields (permission mode, directories, or id) when no rules are present.
    """
    rule_labels = [
        label for label in (describe_permission_rule(rule) for rule in suggestion.rules) if label
    ]
    if rule_labels:
        return ", ".join(rule_labels)

    raw = suggestion.raw
    mode = coerce_text(raw.get("mode")).strip()
    if mode:
        return f"mode: {mode}"
    directories = raw.get("directories")
    if isinstance(directories, list):
        directory_labels = [coerce_text(directory).strip() for directory in directories]
        directory_labels = [label for label in directory_labels if label]
        if directory_labels:
            return "directories: " + ", ".join(directory_labels)
    suggestion_id = coerce_text(raw.get("id")).strip()
    return suggestion_id or "this suggestion"


def build_ask_user_question_response(
    payload: HookPayload,
    answers: dict[str, str],
) -> HookResponse:
    """Build the AskUserQuestion allow response that injects collected answers."""
    updated_input: JsonValue = {
        "questions": payload.tool_input.raw.get("questions", []),
        "answers": dict(answers),
    }
    return HookResponse(
        suppress_output=True,
        hook_specific_output=HookSpecificOutput(
            hook_event_name=HookEventName.PERMISSION_REQUEST,
            decision=PermissionDecision(
                behavior=PermissionBehavior.ALLOW,
                updated_input=updated_input,
            ),
        ),
    )


def build_ask_user_question_cancel_response(payload: HookPayload) -> HookResponse:
    """Build the response sent when the user cancels the AskUserQuestion picker."""
    del payload
    return HookResponse(
        suppress_output=True,
        hook_specific_output=HookSpecificOutput(
            hook_event_name=HookEventName.PERMISSION_REQUEST,
            decision=PermissionDecision(
                behavior=PermissionBehavior.DENY,
                message="Cancelled by local user.",
            ),
        ),
    )


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
