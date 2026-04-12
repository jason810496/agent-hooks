"""Orchestrate normalized payload processing."""

from __future__ import annotations

from pathlib import Path

from agent_hooks.enums import DialogButton, HookEventName, TransportStatus
from agent_hooks.models import (
    AppleScriptDialogResponse,
    AppleScriptResult,
    HookInput,
    HookPayload,
    HookProcessingResult,
    HookResponse,
)
from agent_hooks.presentation import build_notification, build_permission_dialog
from agent_hooks.session_rules import (
    CODEX_SUPPORT_NATIVE_ASK_AND_ALLOW_TOOL_USE,
    load_session_rules,
    matches_session_rule,
    store_session_rule,
)
from agent_hooks.transport import DisplayTransport

DEFAULT_HOOK_RESPONSE = HookResponse()


def process_hook(
    input_data: HookInput,
    transport: DisplayTransport,
    *,
    session_rules_directory: Path | None = None,
) -> HookProcessingResult:
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
        return process_permission_request(
            payload,
            transport,
            current_error=error,
            session_rules_directory=session_rules_directory,
        )

    return process_notification_event(payload, transport, current_error=error)


def process_permission_request(
    payload: HookPayload,
    transport: DisplayTransport,
    *,
    current_error: str | None = None,
    session_rules_directory: Path | None = None,
) -> HookProcessingResult:
    """Process a permission request through the display transport.

    :param payload: Normalized permission payload.
    :type payload: HookPayload
    :param transport: UI transport implementation.
    :type transport: DisplayTransport
    :param current_error: Existing processing error, if any.
    :type current_error: str | None
    :return: Processing result for logging and emission.
    """
    if (
        not CODEX_SUPPORT_NATIVE_ASK_AND_ALLOW_TOOL_USE
        and payload.provider.value == "codex"
        and session_rules_directory is not None
    ):
        stored_rules = load_session_rules(
            session_rules_directory, payload.provider, payload.session_id
        )
        if matches_session_rule(payload, stored_rules):
            return HookProcessingResult(
                display=None,
                transport_result=None,
                response=DEFAULT_HOOK_RESPONSE,
                error=current_error,
            )

    dialog = build_permission_dialog(payload)
    dialog_result = transport.show_dialog(dialog)
    response = (
        build_permission_response(dialog_result.button, payload)
        if dialog_result.button is not None
        else DEFAULT_HOOK_RESPONSE
    )
    if (
        not CODEX_SUPPORT_NATIVE_ASK_AND_ALLOW_TOOL_USE
        and payload.provider.value == "codex"
        and dialog_result.button is not None
        and dialog_result.button.value == "Always Allow"
        and session_rules_directory is not None
        and payload.tool_name
        and payload.tool_input.command
    ):
        store_session_rule(
            session_rules_directory,
            payload.provider,
            payload.session_id,
            payload.tool_name,
            payload.tool_input.command,
        )
    return HookProcessingResult(
        display=dialog,
        transport_result=dialog_result.transport,
        response=response,
        error=transport_error(dialog_result.transport, current_error),
    )


def process_notification_event(
    payload: HookPayload,
    transport: DisplayTransport,
    *,
    current_error: str | None = None,
) -> HookProcessingResult:
    """Process a notification-like event through the display transport.

    :param payload: Normalized hook payload.
    :type payload: HookPayload
    :param transport: UI transport implementation.
    :type transport: DisplayTransport
    :param current_error: Existing processing error, if any.
    :type current_error: str | None
    :return: Processing result for logging and emission.
    """
    notification = build_notification(payload)
    if notification is None:
        return HookProcessingResult(
            display=None,
            transport_result=None,
            response=DEFAULT_HOOK_RESPONSE,
            error=current_error,
        )

    transport_result = transport.send_notification(notification)
    return HookProcessingResult(
        display=notification,
        transport_result=transport_result,
        response=DEFAULT_HOOK_RESPONSE,
        error=transport_error(transport_result, current_error),
    )


def build_permission_response(
    button: DialogButton, payload: HookPayload
) -> AppleScriptDialogResponse:
    """Build the permission response for a selected dialog button.

    :param button: Selected dialog button.
    :type button: DialogButton
    :param payload: Normalized hook payload.
    :type payload: HookPayload
    :return: Structured permission response model.
    """
    return AppleScriptDialogResponse(button=button, payload=payload)


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
