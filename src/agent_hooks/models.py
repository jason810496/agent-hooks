"""Define typed data models for callback processing layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, TypeAlias

from agent_hooks.enums import (
    AppleScriptInvocation,
    DialogButton,
    HookControlDecision,
    HookEventName,
    HookProvider,
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
    provider: HookProvider = HookProvider.CLAUDE_CODE
    event_name: HookEventName = HookEventName.UNKNOWN
    raw_event_name: str = ""
    notification_type: NotificationType = NotificationType.UNKNOWN
    raw_notification_type: str = ""
    model: str = ""
    permission_mode: str = ""
    title: str = ""
    message: str = ""
    prompt: str = ""
    source: str = ""
    last_assistant_message: str = ""
    error_details: str = ""
    error: str = ""
    session_id: str = ""
    cwd: str = ""
    transcript_path: str = ""
    turn_id: str = ""
    tool_name: str = ""
    tool_use_id: str = ""
    stop_hook_active: bool = False
    tool_response: JsonValue | None = None
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
    """Store the structured permission decision sent back to a provider."""

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
    decision: PermissionDecision | None = None
    additional_context: str = ""
    permission_decision_reason: str = ""
    updated_input: JsonValue | None = None
    updated_mcp_tool_output: JsonValue | None = None

    def as_payload(self) -> JsonObject:
        """Serialize the normalized hook-specific output block.

        :return: Provider-neutral JSON payload.
        """
        payload: JsonObject = {"hookEventName": self.hook_event_name.value}
        if self.decision is not None:
            payload["decision"] = self.decision.as_payload()
        if self.additional_context:
            payload["additionalContext"] = self.additional_context
        if self.permission_decision_reason:
            payload["permissionDecisionReason"] = self.permission_decision_reason
        if self.updated_input is not None:
            payload["updatedInput"] = self.updated_input
        if self.updated_mcp_tool_output is not None:
            payload["updatedMCPToolOutput"] = self.updated_mcp_tool_output
        return payload


class HookResponseProtocol(Protocol):
    """Define the protocol implemented by serializable hook responses."""

    suppress_output: bool
    hook_specific_output: HookSpecificOutput | None

    def as_payload(self) -> JsonObject:
        """Serialize the response into Claude's hook payload format."""
        ...


@dataclass(frozen=True)
class HookResponse:
    """Store the top-level response emitted to stdout."""

    suppress_output: bool = True
    hook_specific_output: HookSpecificOutput | None = None
    continue_: bool | None = None
    stop_reason: str = ""
    system_message: str = ""
    decision: HookControlDecision | None = None
    reason: str = ""

    def as_payload(self) -> JsonObject:
        """Serialize the provider-neutral top-level hook response.

        :return: Provider-neutral JSON payload.
        """
        payload: JsonObject = {"suppressOutput": self.suppress_output}
        if self.continue_ is not None:
            payload["continue"] = self.continue_
        if self.stop_reason:
            payload["stopReason"] = self.stop_reason
        if self.system_message:
            payload["systemMessage"] = self.system_message
        if self.decision is not None:
            payload["decision"] = self.decision.value
        if self.reason:
            payload["reason"] = self.reason
        if self.hook_specific_output is not None:
            payload["hookSpecificOutput"] = self.hook_specific_output.as_payload()
        return payload


@dataclass(frozen=True)
class AppleScriptDialogResponse:
    """Store the permission response for one AppleScript dialog selection."""

    button: DialogButton
    payload: HookPayload
    suppress_output: bool = True

    @property
    def hook_specific_output(self) -> HookSpecificOutput | None:
        """Build the permission-specific output block."""
        if self.payload.provider == HookProvider.CODEX:
            return _build_codex_hook_specific_output(self.button)
        else:
            decision = _build_claude_permission_decision(self.button, self.payload)

        return HookSpecificOutput(
            hook_event_name=HookEventName.PERMISSION_REQUEST,
            decision=decision,
            permission_decision_reason=(
                "Permission denied by local user." if self.button == DialogButton.DENY else ""
            ),
        )

    def as_payload(self) -> JsonObject:
        """Serialize the dialog selection into Claude's hook payload format.

        :return: JSON payload for Claude's hook protocol.
        """
        return HookResponse(
            suppress_output=self.suppress_output,
            hook_specific_output=self.hook_specific_output,
        ).as_payload()


def _build_claude_permission_decision(
    button: DialogButton,
    payload: HookPayload,
) -> PermissionDecision:
    """Build the Claude Code permission decision for one dialog button."""
    if button == DialogButton.DENY:
        return PermissionDecision(behavior=PermissionBehavior.DENY)

    updates: tuple[PermissionUpdate, ...] = ()
    if button == DialogButton.ALWAYS_ALLOW:
        updates = tuple(
            PermissionUpdate(source=suggestion.raw) for suggestion in payload.permission_suggestions
        )
    return PermissionDecision(
        behavior=PermissionBehavior.ALLOW,
        updated_permissions=updates,
    )


def _build_codex_permission_decision(button: DialogButton) -> PermissionDecision:
    """Build the Codex PreToolUse permission decision for one dialog button."""
    return PermissionDecision(behavior=PermissionBehavior.DENY)


def _build_codex_hook_specific_output(button: DialogButton) -> HookSpecificOutput | None:
    """Build Codex PreToolUse output for one dialog button."""
    if button != DialogButton.DENY:
        return None

    return HookSpecificOutput(
        hook_event_name=HookEventName.PERMISSION_REQUEST,
        decision=_build_codex_permission_decision(button),
        permission_decision_reason="Permission denied by local user.",
    )


@dataclass(frozen=True)
class HookProcessingResult:
    """Store the processing result before logging and emission."""

    display: DisplaySpec | None
    transport_result: AppleScriptResult | None
    response: HookResponseProtocol
    error: str | None = None


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
