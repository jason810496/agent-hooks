"""Orchestrate normalized payload processing."""

from __future__ import annotations

from agent_hooks.enums import DialogButton, HookEventName, PermissionBehavior, TransportStatus
from agent_hooks.models import (
    AppleScriptResult,
    HookInput,
    HookPayload,
    HookProcessingResult,
    HookResponse,
    HookSpecificOutput,
    PermissionDecision,
    PermissionUpdate,
)
from agent_hooks.presentation import build_notification, build_permission_dialog
from agent_hooks.transport import DisplayTransport

DEFAULT_HOOK_RESPONSE = HookResponse()


def process_hook(input_data: HookInput, transport: DisplayTransport) -> HookProcessingResult:
    """Process a parsed hook payload into a response and optional UI action.

    :param input_data: Parsed hook input.
    :type input_data: HookInput
    :param transport: UI transport implementation.
    :type transport: DisplayTransport
    :return: Processing result for logging and emission.
    """
    error = input_data.parse_error
    if input_data.parse_error is not None:
        return HookProcessingResult(
            display=None,
            transport_result=None,
            response=DEFAULT_HOOK_RESPONSE,
            error=input_data.parse_error,
        )

    payload = input_data.payload
    if payload.event_name == HookEventName.PERMISSION_REQUEST:
        dialog = build_permission_dialog(payload)
        dialog_result = transport.show_dialog(dialog)
        response = (
            build_permission_response(dialog_result.button, payload)
            if dialog_result.button is not None
            else DEFAULT_HOOK_RESPONSE
        )
        return HookProcessingResult(
            display=dialog,
            transport_result=dialog_result.transport,
            response=response,
            error=transport_error(dialog_result.transport, error),
        )

    notification = build_notification(payload)
    if notification is None:
        return HookProcessingResult(
            display=None,
            transport_result=None,
            response=DEFAULT_HOOK_RESPONSE,
            error=error,
        )

    transport_result = transport.send_notification(notification)
    return HookProcessingResult(
        display=notification,
        transport_result=transport_result,
        response=DEFAULT_HOOK_RESPONSE,
        error=transport_error(transport_result, error),
    )


def build_permission_response(button: DialogButton, payload: HookPayload) -> HookResponse:
    """Build the permission response for a selected dialog button.

    :param button: Selected dialog button.
    :type button: DialogButton
    :param payload: Normalized hook payload.
    :type payload: HookPayload
    :return: Structured hook response.
    """
    if button == DialogButton.DENY:
        decision = PermissionDecision(behavior=PermissionBehavior.DENY)
    else:
        updates = ()
        if button == DialogButton.ALWAYS_ALLOW:
            updates = tuple(
                PermissionUpdate(source=suggestion.raw)
                for suggestion in payload.permission_suggestions
            )
        decision = PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            updated_permissions=updates,
        )

    return HookResponse(
        suppress_output=True,
        hook_specific_output=HookSpecificOutput(
            hook_event_name=HookEventName.PERMISSION_REQUEST,
            decision=decision,
        ),
    )


def transport_error(transport_result: object, current_error: str | None) -> str | None:
    """Return the effective error after a transport action.

    :param transport_result: Transport result to inspect.
    :type transport_result: object
    :param current_error: Existing error, if any.
    :type current_error: str | None
    :return: Effective error string, or ``None`` when no error exists.
    """
    if current_error is not None:
        return current_error

    if not isinstance(transport_result, AppleScriptResult):
        return current_error

    status = transport_result.status
    if status != TransportStatus.FAILED:
        return None

    stderr = transport_result.stderr
    return stderr or "osascript exited non-zero"
