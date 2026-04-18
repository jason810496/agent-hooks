"""Deny high-risk Git operations against protected branches."""

from __future__ import annotations

from example_utils import tokenize_command

from agent_hooks import (
    AgentHook,
    AppleScriptDialogResponse,
    PermissionRequestEvent,
    build_permission_response,
)
from agent_hooks.enums import DialogButton

FORCE_PUSH_FLAGS = frozenset({"--force", "--force-with-lease", "-f"})
PROTECTED_BRANCHES = frozenset({"main", "master", "release"})

app = AgentHook(fallback_to_default_processor=False)


def token_targets_protected_branch(token: str) -> bool:
    """Return whether a Git argument references a protected branch.

    :param token: One Git command argument.
    :type token: str
    :return: ``True`` when the token references a protected branch.
    """
    normalized_token = token.lower()
    if normalized_token in PROTECTED_BRANCHES:
        return True
    return normalized_token.endswith(":main") or normalized_token.endswith(":master")


def command_is_risky_git_operation(argv: list[str]) -> bool:
    """Return whether a tokenized Git command should be denied.

    :param argv: Tokenized shell command.
    :type argv: list[str]
    :return: ``True`` when the command targets protected history or branches.
    """
    if argv[:2] == ["git", "push"]:
        if any(flag in FORCE_PUSH_FLAGS for flag in argv[2:]):
            return True
        return any(token_targets_protected_branch(token) for token in argv[2:])

    if argv[:2] == ["git", "commit"] and "--amend" in argv[2:]:
        return True
    return argv[:2] == ["git", "reset"] and "--hard" in argv[2:]


@app.permission()
def permission_handler(hook_event: PermissionRequestEvent) -> AppleScriptDialogResponse:
    """Allow ordinary Git usage while denying protected-branch mutations.

    :param hook_event: Normalized permission event from Agent Hooks.
    :type hook_event: PermissionRequestEvent
    :return: Provider-specific permission response.
    """
    if hook_event.tool_name != "Bash":
        return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)

    argv = tokenize_command(hook_event.tool_input.command)
    if argv[:1] != ["git"]:
        return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)

    if command_is_risky_git_operation(argv):
        return build_permission_response(DialogButton.DENY, hook_event)

    return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)
