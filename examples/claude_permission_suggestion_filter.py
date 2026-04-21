"""Apply only reviewed Claude permission suggestions as session rules."""

from __future__ import annotations

from agent_hooks import (
    AgentHook,
    AppleScriptDialogResponse,
    HookProvider,
    HookResponse,
    PermissionRequestEvent,
    build_permission_response,
)
from agent_hooks.enums import DialogButton, HookEventName, PermissionBehavior
from agent_hooks.models.response import HookSpecificOutput, PermissionDecision, PermissionUpdate

SAFE_BASH_RULE_PREFIXES = (
    "find ",
    "git diff",
    "git log",
    "git show",
    "git status",
    "ls",
    "pwd",
    "rg ",
)

app = AgentHook(fallback_to_default_processor=False, provider=HookProvider.CLAUDE_CODE)


def command_is_safe(command: str) -> bool:
    """Return whether a requested Bash command is safe for session reuse.

    :param command: Raw Bash command from the hook payload.
    :type command: str
    :return: ``True`` when the command matches the small reviewable allowlist.
    """
    normalized_command = command.strip()
    return any(
        normalized_command == prefix or normalized_command.startswith(prefix)
        for prefix in SAFE_BASH_RULE_PREFIXES
    )


def extract_suggestion_objects(raw_payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    """Extract permission suggestion objects from the Claude raw payload.

    :param raw_payload: Raw callback payload preserved by Agent Hooks.
    :type raw_payload: dict[str, object]
    :return: Tuple of suggestion objects.
    """
    raw_suggestions = raw_payload.get("permission_suggestions")
    if not isinstance(raw_suggestions, list):
        return ()

    suggestions: list[dict[str, object]] = []
    for suggestion in raw_suggestions:
        if isinstance(suggestion, dict):
            suggestions.append(dict(suggestion))
    return tuple(suggestions)


def rule_is_safe(rule: dict[str, object]) -> bool:
    """Return whether one Claude permission rule is safe enough to persist.

    :param rule: Raw rule object from a Claude permission suggestion.
    :type rule: dict[str, object]
    :return: ``True`` when the rule is specific and read-only.
    """
    tool_name = str(rule.get("toolName", "")).strip()
    rule_content = str(rule.get("ruleContent", "")).strip()
    if tool_name != "Bash" or not rule_content:
        return False
    if "*" in rule_content:
        return False
    return any(
        rule_content == prefix or rule_content.startswith(prefix)
        for prefix in SAFE_BASH_RULE_PREFIXES
    )


def filter_safe_suggestions(raw_payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    """Keep only suggestion objects whose rules are fully reviewed as safe.

    :param raw_payload: Raw callback payload preserved by Agent Hooks.
    :type raw_payload: dict[str, object]
    :return: Tuple of safe suggestion objects.
    """
    safe_suggestions: list[dict[str, object]] = []
    for suggestion in extract_suggestion_objects(raw_payload):
        raw_rules = suggestion.get("rules")
        if not isinstance(raw_rules, list) or not raw_rules:
            continue

        rules = [dict(rule) for rule in raw_rules if isinstance(rule, dict)]
        if rules and all(rule_is_safe(rule) for rule in rules):
            safe_suggestions.append(suggestion)
    return tuple(safe_suggestions)


@app.permission()
def permission_handler(
    hook_event: PermissionRequestEvent,
) -> HookResponse | AppleScriptDialogResponse:
    """Allow once by default and persist only reviewed Claude rules.

    :param hook_event: Claude permission request normalized by Agent Hooks.
    :type hook_event: PermissionRequestEvent
    :return: Response that either allows once, denies, or applies filtered session rules.
    """
    if hook_event.tool_name != "Bash":
        return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)

    command = hook_event.tool_input.command.strip()
    if not command_is_safe(command):
        return build_permission_response(DialogButton.DENY, hook_event)

    safe_suggestions = filter_safe_suggestions(hook_event.raw)
    if not safe_suggestions:
        return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)

    return HookResponse(
        hook_specific_output=HookSpecificOutput(
            hook_event_name=HookEventName.PERMISSION_REQUEST,
            decision=PermissionDecision(
                behavior=PermissionBehavior.ALLOW,
                updated_permissions=tuple(
                    PermissionUpdate(source=suggestion) for suggestion in safe_suggestions
                ),
            ),
        )
    )
