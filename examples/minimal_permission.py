"""Show the smallest provider-neutral permission app."""

from __future__ import annotations

from agent_hooks import (
    AgentHook,
    AppleScriptDialogResponse,
    PermissionRequestEvent,
    build_permission_response,
)
from agent_hooks.enums import DialogButton

SAFE_BASH_PREFIXES = (
    "pwd",
    "ls",
    "find ",
    "rg ",
    "git status",
    "git diff",
    "git show",
    "git log",
)
SAFE_FILE_TOOLS = frozenset({"Read", "Glob", "Grep", "LS"})

app = AgentHook(fallback_to_default_processor=False)


def command_is_safe(command: str) -> bool:
    """Return whether a Bash command is safe enough for automatic allow-once.

    :param command: Raw command string from the hook payload.
    :type command: str
    :return: ``True`` when the command matches the example allowlist.
    """
    normalized_command = command.strip()
    return any(
        normalized_command == prefix or normalized_command.startswith(prefix)
        for prefix in SAFE_BASH_PREFIXES
    )


@app.permission()
def permission_handler(hook_event: PermissionRequestEvent) -> AppleScriptDialogResponse:
    """Handle one normalized permission request.

    :param hook_event: Permission request exposed by Agent Hooks.
    :type hook_event: PermissionRequestEvent
    :return: Provider-specific allow or deny response.
    """
    if hook_event.tool_name == "Bash" and command_is_safe(hook_event.tool_input.command):
        return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)

    if hook_event.tool_name in SAFE_FILE_TOOLS:
        return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)

    return build_permission_response(DialogButton.DENY, hook_event)
