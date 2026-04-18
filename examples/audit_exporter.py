"""Export normalized hook events to a compact JSONL audit stream."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from example_utils import (
    append_jsonl,
    compact_text,
    now_timestamp,
    resolve_state_directory,
)

from agent_hooks import AgentHook
from agent_hooks.middleware import HookMiddlewareContext
from agent_hooks.models import HookProcessingResult

AUDIT_DIRECTORY_ENV_VAR = "AGENT_HOOK_AUDIT_EXPORT_DIR"
DEFAULT_AUDIT_DIRECTORY = ".agent-hooks/audit-export"

app = AgentHook()


def resolve_audit_path(cwd: str) -> Path:
    """Resolve the JSONL path used by the exporter.

    :param cwd: Working directory from the hook payload.
    :type cwd: str
    :return: Audit JSONL file path.
    """
    audit_directory = resolve_state_directory(
        cwd,
        env_var=AUDIT_DIRECTORY_ENV_VAR,
        default_subdir=DEFAULT_AUDIT_DIRECTORY,
    )
    return audit_directory / "hooks.jsonl"


@app.middleware()
def audit_middleware(
    context: HookMiddlewareContext,
    call_next: Callable[[HookMiddlewareContext], HookProcessingResult],
) -> HookProcessingResult:
    """Write one compact audit record before normal callback processing continues.

    :param context: Middleware context for the current callback.
    :type context: HookMiddlewareContext
    :param call_next: Remaining middleware and dispatch chain.
    :type call_next: collections.abc.Callable[[HookMiddlewareContext], HookProcessingResult]
    :return: Hook processing result from the remainder of the dispatch chain.
    """
    payload = context.payload
    append_jsonl(
        resolve_audit_path(payload.cwd),
        {
            "timestamp": now_timestamp(),
            "provider": payload.provider.value,
            "event_name": payload.event_name.value,
            "raw_event_name": payload.raw_event_name,
            "session_id": payload.session_id,
            "cwd": payload.cwd,
            "tool_name": payload.tool_name,
            "command": compact_text(payload.tool_input.command, limit=400),
            "file_path": payload.tool_input.file_path,
            "prompt": compact_text(payload.prompt, limit=400),
            "message": compact_text(payload.message, limit=400),
            "last_assistant_message": compact_text(payload.last_assistant_message, limit=400),
        },
    )
    return call_next(context)
