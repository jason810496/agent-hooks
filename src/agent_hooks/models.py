"""Define typed data models for callback processing layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

from agent_hooks.enums import (
    AppleScriptInvocation,
    DialogButton,
    HookEventName,
    NotificationSound,
    NotificationType,
    PermissionBehavior,
    PermissionDestination,
    TransportStatus,
)

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True)
class PermissionRule:
    """Store one suggested Claude permission rule."""

    tool_name: str = ""
    rule_content: str = ""
    raw: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class PermissionSuggestion:
    """Store one Claude permission suggestion payload."""

    raw: JsonObject = field(default_factory=dict)
    rules: tuple[PermissionRule, ...] = ()


@dataclass(frozen=True)
class ToolInput:
    """Store normalized tool input values for display decisions."""

    raw: JsonObject = field(default_factory=dict)
    command: str = ""
    file_path: str = ""
    description: str = ""
    url: str = ""
    query: str = ""
    prompt: str = ""
    pattern: str = ""


@dataclass(frozen=True)
class HookPayload:
    """Store the normalized hook payload used by processing logic."""

    raw: JsonObject = field(default_factory=dict)
    event_name: HookEventName = HookEventName.UNKNOWN
    raw_event_name: str = ""
    notification_type: NotificationType = NotificationType.UNKNOWN
    raw_notification_type: str = ""
    title: str = ""
    message: str = ""
    last_assistant_message: str = ""
    error_details: str = ""
    error: str = ""
    session_id: str = ""
    cwd: str = ""
    tool_name: str = ""
    tool_input: ToolInput = field(default_factory=ToolInput)
    permission_suggestions: tuple[PermissionSuggestion, ...] = ()


@dataclass(frozen=True)
class HookInput:
    """Store the raw stdin payload and parse outcome."""

    raw_input: str
    payload: HookPayload
    parse_error: str | None = None


@dataclass(frozen=True)
class NotificationSpec:
    """Store a macOS notification request."""

    title: str
    message: str
    subtitle: str = ""
    sound: NotificationSound = NotificationSound.NONE


@dataclass(frozen=True)
class DialogSpec:
    """Store an interactive macOS dialog request."""

    title: str
    message: str
    buttons: tuple[DialogButton, ...]
    default_button: DialogButton


DisplaySpec: TypeAlias = NotificationSpec | DialogSpec


@dataclass(frozen=True)
class AppleScriptResult:
    """Store the result of one AppleScript invocation."""

    status: TransportStatus
    invocation: AppleScriptInvocation
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    skipped_reason: str = ""


@dataclass(frozen=True)
class DialogResult:
    """Store a dialog selection and its transport metadata."""

    button: DialogButton | None
    transport: AppleScriptResult


@dataclass(frozen=True)
class PermissionUpdate:
    """Store one outgoing permission update for Claude."""

    source: JsonObject
    destination: PermissionDestination = PermissionDestination.SESSION

    def as_payload(self) -> JsonObject:
        """Serialize the permission update for Claude.

        :return: JSON payload with destination override applied.
        """
        return {**self.source, "destination": self.destination.value}


@dataclass(frozen=True)
class PermissionDecision:
    """Store the structured permission decision sent back to Claude."""

    behavior: PermissionBehavior
    updated_permissions: tuple[PermissionUpdate, ...] = ()

    def as_payload(self) -> JsonObject:
        """Serialize the permission decision.

        :return: JSON payload for Claude's hook protocol.
        """
        payload: JsonObject = {"behavior": self.behavior.value}
        if self.updated_permissions:
            payload["updatedPermissions"] = [
                update.as_payload() for update in self.updated_permissions
            ]
        return payload


@dataclass(frozen=True)
class HookSpecificOutput:
    """Store hook-event-specific response content."""

    hook_event_name: HookEventName
    decision: PermissionDecision

    def as_payload(self) -> JsonObject:
        """Serialize the hook-specific output block.

        :return: JSON payload for Claude's hook protocol.
        """
        return {
            "hookEventName": self.hook_event_name.value,
            "decision": self.decision.as_payload(),
        }


@dataclass(frozen=True)
class HookResponse:
    """Store the top-level response emitted to stdout."""

    suppress_output: bool = True
    hook_specific_output: HookSpecificOutput | None = None

    def as_payload(self) -> JsonObject:
        """Serialize the top-level hook response.

        :return: JSON payload for Claude's hook protocol.
        """
        payload: JsonObject = {"suppressOutput": self.suppress_output}
        if self.hook_specific_output is not None:
            payload["hookSpecificOutput"] = self.hook_specific_output.as_payload()
        return payload


@dataclass(frozen=True)
class HookProcessingResult:
    """Store the processing result before logging and emission."""

    display: DisplaySpec | None
    transport_result: AppleScriptResult | None
    response: HookResponse
    error: str | None = None


@dataclass(frozen=True)
class HookLogRecord:
    """Store the structured log entry for one callback execution."""

    timestamp: str
    log_path: Path
    raw_log_path: Path
    raw_input: str
    hook_event_name: str
    payload: JsonObject
    display: DisplaySpec | None
    osascript: AppleScriptResult | None
    hook_response: JsonObject
    error: str | None = None
