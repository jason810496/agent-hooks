"""Deny tool access that escapes the current repository boundary."""

from __future__ import annotations

from pathlib import Path

from example_utils import (
    command_path_tokens,
    path_is_sensitive,
    path_is_within_root,
    resolve_path_token,
)

from agent_hooks import (
    AgentHook,
    AppleScriptDialogResponse,
    PermissionRequestEvent,
    build_permission_response,
)
from agent_hooks.enums import DialogButton

LOCAL_FILE_TOOLS = frozenset({"Edit", "Glob", "Grep", "LS", "MultiEdit", "Read", "Write"})
SAFE_BASH_PREFIXES = (
    "git diff",
    "git status",
    "ls",
    "pwd",
    "rg ",
)

app = AgentHook(fallback_to_default_processor=False)


def collect_referenced_paths(hook_event: PermissionRequestEvent) -> tuple[str, ...]:
    """Collect raw path references from the hook event.

    :param hook_event: Normalized permission event from Agent Hooks.
    :type hook_event: PermissionRequestEvent
    :return: Raw path strings referenced by the tool request.
    """
    collected_paths: list[str] = []
    if hook_event.tool_input.file_path:
        collected_paths.append(hook_event.tool_input.file_path)
    if hook_event.tool_input.command:
        collected_paths.extend(command_path_tokens(hook_event.tool_input.command))
    return tuple(collected_paths)


def request_escapes_repository(hook_event: PermissionRequestEvent) -> bool:
    """Return whether the request escapes ``cwd`` or touches sensitive paths.

    :param hook_event: Normalized permission event from Agent Hooks.
    :type hook_event: PermissionRequestEvent
    :return: ``True`` when any referenced path should be denied.
    """
    if not hook_event.cwd:
        return False

    project_root = Path(hook_event.cwd).resolve(strict=False)
    for raw_path in collect_referenced_paths(hook_event):
        resolved_path = resolve_path_token(raw_path, hook_event.cwd)
        if resolved_path is None:
            continue
        if path_is_sensitive(resolved_path):
            return True
        if not path_is_within_root(resolved_path, project_root):
            return True
    return False


def command_is_safe_without_paths(command: str) -> bool:
    """Return whether a Bash command is safe even without explicit paths.

    :param command: Raw Bash command from the hook payload.
    :type command: str
    :return: ``True`` when the command matches the small safe allowlist.
    """
    normalized_command = command.strip()
    return any(
        normalized_command == prefix or normalized_command.startswith(prefix)
        for prefix in SAFE_BASH_PREFIXES
    )


@app.permission()
def permission_handler(hook_event: PermissionRequestEvent) -> AppleScriptDialogResponse:
    """Allow repository-local access and deny boundary escapes.

    :param hook_event: Normalized permission event from Agent Hooks.
    :type hook_event: PermissionRequestEvent
    :return: Provider-specific permission response.
    """
    if request_escapes_repository(hook_event):
        return build_permission_response(DialogButton.DENY, hook_event)

    if hook_event.tool_name in LOCAL_FILE_TOOLS and collect_referenced_paths(hook_event):
        return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)

    if hook_event.tool_name == "Bash":
        command = hook_event.tool_input.command.strip()
        if not command:
            return build_permission_response(DialogButton.DENY, hook_event)

        if collect_referenced_paths(hook_event) or command_is_safe_without_paths(command):
            return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)

    return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)
