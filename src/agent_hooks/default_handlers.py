"""Provide built-in fallback handlers for unhandled hook events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from agent_hooks.enums import DialogButton, HookEventName, TransportStatus
from agent_hooks.models.schemas.display import AppleScriptResult
from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.models.schemas.processing import HookProcessingResult
from agent_hooks.models.schemas.responses import AppleScriptDialogResponse, HookResponse
from agent_hooks.providers import provider_client
from agent_hooks.transport import DisplayTransport

if TYPE_CHECKING:
    from agent_hooks.models.events import (
        HookEvent,
        NotificationEvent,
        PermissionRequestEvent,
        StopEvent,
        StopFailureEvent,
    )

DEFAULT_HOOK_RESPONSE = HookResponse()


class HookFallbackHandler(Protocol):
    """Define the fallback interface used by ``AgentHook``."""

    def handle(
        self,
        payload: HookPayload,
        transport: DisplayTransport,
        *,
        current_error: str | None = None,
    ) -> HookProcessingResult:
        """Handle one unhandled normalized hook payload.

        :param payload: Normalized hook payload.
        :type payload: HookPayload
        :param transport: UI transport implementation.
        :type transport: DisplayTransport
        :param current_error: Existing processing error, if any.
        :type current_error: str | None
        :return: Processing result for logging and emission.
        """
        ...


class DefaultHookHandler:
    """Handle built-in permission dialogs and notifications."""

    def handle(
        self,
        payload: HookPayload | HookEvent,
        transport: DisplayTransport,
        *,
        current_error: str | None = None,
    ) -> HookProcessingResult:
        """Handle one unhandled hook payload with built-in behavior.

        :param payload: Normalized hook payload.
        :type payload: HookPayload | HookEvent
        :param transport: UI transport implementation.
        :type transport: DisplayTransport
        :param current_error: Existing processing error, if any.
        :type current_error: str | None
        :return: Processing result for logging and emission.
        """
        normalized_payload = cast(HookPayload, payload)
        if normalized_payload.event_name == HookEventName.PERMISSION_REQUEST:
            return self.handle_permission_request(
                normalized_payload,
                transport,
                current_error=current_error,
            )

        return self.handle_notification_event(
            normalized_payload,
            transport,
            current_error=current_error,
        )

    def handle_permission_request(
        self,
        payload: HookPayload | PermissionRequestEvent,
        transport: DisplayTransport,
        *,
        current_error: str | None = None,
    ) -> HookProcessingResult:
        """Handle a permission request through the display transport.

        :param payload: Normalized permission payload.
        :type payload: HookPayload | PermissionRequestEvent
        :param transport: UI transport implementation.
        :type transport: DisplayTransport
        :param current_error: Existing processing error, if any.
        :type current_error: str | None
        :return: Processing result for logging and emission.
        """
        normalized_payload = cast(HookPayload, payload)
        dialog = provider_client.build_permission_dialog(normalized_payload)
        dialog_result = transport.show_dialog(dialog)
        response = (
            self.build_permission_response(dialog_result.button, normalized_payload)
            if dialog_result.button is not None
            else DEFAULT_HOOK_RESPONSE
        )
        return HookProcessingResult(
            display=dialog,
            transport_result=dialog_result.transport,
            response=response,
            error=self.transport_error(dialog_result.transport, current_error),
        )

    def handle_notification_event(
        self,
        payload: HookPayload | NotificationEvent | StopEvent | StopFailureEvent,
        transport: DisplayTransport,
        *,
        current_error: str | None = None,
    ) -> HookProcessingResult:
        """Handle a notification-like event through the display transport.

        :param payload: Normalized hook payload.
        :type payload: HookPayload | NotificationEvent | StopEvent | StopFailureEvent
        :param transport: UI transport implementation.
        :type transport: DisplayTransport
        :param current_error: Existing processing error, if any.
        :type current_error: str | None
        :return: Processing result for logging and emission.
        """
        notification = provider_client.build_notification(cast(HookPayload, payload))
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
            error=self.transport_error(transport_result, current_error),
        )

    def build_permission_response(
        self,
        button: DialogButton,
        payload: HookPayload | PermissionRequestEvent,
    ) -> AppleScriptDialogResponse:
        """Build the permission response for a selected dialog button.

        :param button: Selected dialog button.
        :type button: DialogButton
        :param payload: Normalized hook payload.
        :type payload: HookPayload | PermissionRequestEvent
        :return: Structured permission response model.
        """
        return provider_client.build_permission_response(button, cast(HookPayload, payload))

    def transport_error(self, transport_result: object, current_error: str | None) -> str | None:
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


_DEFAULT_HANDLER = DefaultHookHandler()


def process_permission_request(
    payload: HookPayload | PermissionRequestEvent,
    transport: DisplayTransport,
    *,
    current_error: str | None = None,
) -> HookProcessingResult:
    """Handle a permission request with the built-in fallback handler.

    :param payload: Normalized permission payload.
    :type payload: HookPayload | PermissionRequestEvent
    :param transport: UI transport implementation.
    :type transport: DisplayTransport
    :param current_error: Existing processing error, if any.
    :type current_error: str | None
    :return: Processing result for logging and emission.
    """
    return _DEFAULT_HANDLER.handle_permission_request(
        payload,
        transport,
        current_error=current_error,
    )


def process_notification_event(
    payload: HookPayload | NotificationEvent | StopEvent | StopFailureEvent,
    transport: DisplayTransport,
    *,
    current_error: str | None = None,
) -> HookProcessingResult:
    """Handle a notification-like event with the built-in fallback handler.

    :param payload: Normalized hook payload.
    :type payload: HookPayload | NotificationEvent | StopEvent | StopFailureEvent
    :param transport: UI transport implementation.
    :type transport: DisplayTransport
    :param current_error: Existing processing error, if any.
    :type current_error: str | None
    :return: Processing result for logging and emission.
    """
    return _DEFAULT_HANDLER.handle_notification_event(
        payload,
        transport,
        current_error=current_error,
    )


def build_permission_response(
    button: DialogButton,
    payload: HookPayload | PermissionRequestEvent,
) -> AppleScriptDialogResponse:
    """Build the permission response for a selected dialog button.

    :param button: Selected dialog button.
    :type button: DialogButton
    :param payload: Normalized hook payload.
    :type payload: HookPayload | PermissionRequestEvent
    :return: Structured permission response model.
    """
    return _DEFAULT_HANDLER.build_permission_response(button, payload)


def transport_error(transport_result: object, current_error: str | None) -> str | None:
    """Return the effective error after a transport action.

    :param transport_result: Transport result to inspect.
    :type transport_result: object
    :param current_error: Existing error, if any.
    :type current_error: str | None
    :return: Effective error string, or ``None`` when no error exists.
    """
    return _DEFAULT_HANDLER.transport_error(transport_result, current_error)


__all__ = [
    "DEFAULT_HOOK_RESPONSE",
    "DefaultHookHandler",
    "HookFallbackHandler",
    "build_permission_response",
    "process_notification_event",
    "process_permission_request",
    "transport_error",
]
