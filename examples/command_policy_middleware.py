"""Show middleware-based command policy shortcuts."""

from __future__ import annotations

import shlex
from collections.abc import Callable

from agent_hooks import AgentHook, build_permission_response
from agent_hooks.enums import DialogButton, HookEventName
from agent_hooks.middleware import HookMiddlewareContext
from agent_hooks.models import HookProcessingResult

SAFE_EXECUTABLES = frozenset(
    {
        "cat",
        "find",
        "git",
        "head",
        "ls",
        "nl",
        "pwd",
        "rg",
        "sed",
        "sort",
        "tail",
        "uniq",
        "wc",
    }
)
BLOCKED_SUBSTRINGS = (
    "rm -rf /",
    "chmod -r 777 /",
    "mkfs",
    "dd if=",
    "cat ~/.ssh",
    "cat .env",
)

app = AgentHook()


def tokenize_command(command: str) -> list[str]:
    """Tokenize a shell command conservatively.

    :param command: Raw shell command from the hook payload.
    :type command: str
    :return: Tokenized arguments, or an empty list on parse failure.
    """
    try:
        return shlex.split(command)
    except ValueError:
        return []


def command_looks_like_pipe_to_shell(command: str) -> bool:
    """Return whether the command looks like a bootstrap pipe into a shell.

    :param command: Raw shell command from the hook payload.
    :type command: str
    :return: ``True`` when the command resembles ``curl | sh`` or similar.
    """
    normalized_command = command.lower()
    has_download = "curl " in normalized_command or "wget " in normalized_command
    has_shell_pipe = "| sh" in normalized_command or "| bash" in normalized_command
    return has_download and has_shell_pipe


def build_short_circuit_result(
    button: DialogButton,
    context: HookMiddlewareContext,
) -> HookProcessingResult:
    """Build a middleware short-circuit result for a permission event.

    :param button: Dialog outcome to synthesize.
    :type button: DialogButton
    :param context: Middleware context for the current callback.
    :type context: HookMiddlewareContext
    :return: Processing result that skips the rest of dispatch.
    """
    return HookProcessingResult(
        display=None,
        transport_result=None,
        response=build_permission_response(button, context.payload),
    )


@app.middleware()
def bash_policy_middleware(
    context: HookMiddlewareContext,
    call_next: Callable[[HookMiddlewareContext], HookProcessingResult],
) -> HookProcessingResult:
    """Short-circuit obviously safe or risky Bash commands.

    :param context: Middleware context for the current callback.
    :type context: HookMiddlewareContext
    :param call_next: Remaining middleware and dispatch chain.
    :type call_next: collections.abc.Callable[[HookMiddlewareContext], HookProcessingResult]
    :return: Middleware result for the callback.
    """
    payload = context.payload
    if payload.event_name != HookEventName.PERMISSION_REQUEST or payload.tool_name != "Bash":
        return call_next(context)

    command = payload.tool_input.command.strip()
    if not command:
        return call_next(context)

    normalized_command = command.lower()
    if any(fragment in normalized_command for fragment in BLOCKED_SUBSTRINGS):
        return build_short_circuit_result(DialogButton.DENY, context)

    if command_looks_like_pipe_to_shell(command):
        return build_short_circuit_result(DialogButton.DENY, context)

    argv = tokenize_command(command)
    executable = argv[0] if argv else ""
    if executable in SAFE_EXECUTABLES:
        return build_short_circuit_result(DialogButton.ALLOW_ONCE, context)

    return call_next(context)
