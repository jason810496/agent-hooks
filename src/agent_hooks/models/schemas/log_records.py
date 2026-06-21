"""Define log record models emitted during callback execution."""

from __future__ import annotations

from dataclasses import dataclass

from agent_hooks.models.schemas.display import AppleScriptResult, DisplaySpec


@dataclass(frozen=True)
class ApplicationLogRecord:
    """Store the application log entry for one callback execution."""

    timestamp: str
    provider: str
    hook_event_name: str
    session_id: str
    cwd: str
    notification_type: str
    tool_name: str
    parse_error: str | None
    display: DisplaySpec | None
    osascript: AppleScriptResult | None
    suppress_output: bool
    has_hook_specific_output: bool
    raw_input_bytes: int
    response_bytes: int
    configuration_warnings: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class InputAuditLogRecord:
    """Store the raw input audit log entry for one callback execution."""

    timestamp: str
    provider: str
    hook_event_name: str
    session_id: str
    cwd: str
    raw_input: str


@dataclass(frozen=True)
class ResponseAuditLogRecord:
    """Store the response audit log entry for one callback execution."""

    timestamp: str
    provider: str
    hook_event_name: str
    session_id: str
    cwd: str
    hook_response: str


__all__ = [
    "ApplicationLogRecord",
    "InputAuditLogRecord",
    "ResponseAuditLogRecord",
]
