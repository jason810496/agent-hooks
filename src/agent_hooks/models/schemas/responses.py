"""Define serialized hook response models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_hooks.enums import DialogButton, HookControlDecision, HookEventName
from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.models.schemas.json_types import JsonObject, JsonValue
from agent_hooks.models.schemas.permissions import PermissionDecision


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
    hook_specific_output: HookSpecificOutput | None = None
    suppress_output: bool = True

    def as_payload(self) -> JsonObject:
        """Serialize the dialog selection into the normalized hook payload format.

        :return: Provider-neutral response payload.
        """
        return HookResponse(
            suppress_output=self.suppress_output,
            hook_specific_output=self.hook_specific_output,
        ).as_payload()


__all__ = [
    "AppleScriptDialogResponse",
    "HookResponse",
    "HookResponseProtocol",
    "HookSpecificOutput",
]
