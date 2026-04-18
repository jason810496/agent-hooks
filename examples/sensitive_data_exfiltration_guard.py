"""Deny commands that try to ship sensitive local files to remote targets."""

from __future__ import annotations

from example_utils import command_mentions_sensitive_path, tokenize_command

from agent_hooks import (
    AgentHook,
    AppleScriptDialogResponse,
    PermissionRequestEvent,
    build_permission_response,
)
from agent_hooks.enums import DialogButton

REMOTE_TARGET_PREFIXES = ("gs://", "http://", "https://", "s3://")
UPLOAD_FLAGS = frozenset({"--data", "--data-binary", "--form", "--upload-file", "-F", "-T", "-d"})

app = AgentHook(fallback_to_default_processor=False)


def command_looks_like_remote_transfer(argv: list[str]) -> bool:
    """Return whether a tokenized command sends data to a remote target.

    :param argv: Tokenized shell command.
    :type argv: list[str]
    :return: ``True`` when the command resembles an upload or remote copy.
    """
    if not argv:
        return False

    executable = argv[0]
    if executable in {"scp", "rsync"}:
        return True
    if executable == "curl" and any(flag in UPLOAD_FLAGS for flag in argv[1:]):
        return True
    return executable == "aws" and argv[1:3] == ["s3", "cp"]


def command_has_remote_target(argv: list[str]) -> bool:
    """Return whether a tokenized command references a remote destination.

    :param argv: Tokenized shell command.
    :type argv: list[str]
    :return: ``True`` when the command contains a remote target token.
    """
    for token in argv[1:]:
        if token.startswith(REMOTE_TARGET_PREFIXES):
            return True
        if "@" in token and ":" in token and not token.startswith(("/", "./", "../", "~")):
            return True
    return False


@app.permission()
def permission_handler(hook_event: PermissionRequestEvent) -> AppleScriptDialogResponse:
    """Allow ordinary commands but deny exfiltration of sensitive files.

    :param hook_event: Normalized permission event from Agent Hooks.
    :type hook_event: PermissionRequestEvent
    :return: Provider-specific permission response.
    """
    if hook_event.tool_name != "Bash":
        return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)

    command = hook_event.tool_input.command.strip()
    argv = tokenize_command(command)
    if (
        command_looks_like_remote_transfer(argv)
        and command_has_remote_target(argv)
        and command_mentions_sensitive_path(command, hook_event.cwd)
    ):
        return build_permission_response(DialogButton.DENY, hook_event)

    return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)
