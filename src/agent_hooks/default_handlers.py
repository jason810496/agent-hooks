"""Provide built-in fallback handlers for unhandled hook events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from agent_hooks.enums import DialogButton, HookEventName, HookProvider, TransportStatus
from agent_hooks.models.schemas.display import (
    FREE_TEXT_ALLOW_NOTE,
    AppleScriptResult,
    FreeText,
)
from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.models.schemas.processing import HookProcessingResult
from agent_hooks.models.schemas.responses import AppleScriptDialogResponse, HookResponse
from agent_hooks.providers import provider_client
from agent_hooks.providers.claude_code.permissions import (
    build_allow_with_context_response,
    build_ask_user_question_cancel_response,
    build_ask_user_question_response,
    build_correction_response,
    build_permission_choice_response,
)
from agent_hooks.providers.claude_code.presentation import (
    build_ask_user_question_dialog,
    build_permission_choice_dialog,
    is_ask_user_question_payload,
    is_permission_choice_payload,
)
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
        if is_ask_user_question_payload(normalized_payload):
            ask_result, current_error = self.handle_ask_user_question(
                normalized_payload,
                transport,
                current_error=current_error,
            )
            if ask_result is not None:
                return ask_result

        if is_permission_choice_payload(normalized_payload):
            choice_result, current_error = self.handle_permission_choice(
                normalized_payload,
                transport,
                current_error=current_error,
            )
            if choice_result is not None:
                return choice_result

        dialog = provider_client.build_permission_dialog(normalized_payload)
        dialog_result = transport.show_dialog(dialog)
        free_text_response = self._free_text_response(
            normalized_payload, dialog_result.free_text
        )
        if free_text_response is not None:
            response: HookResponse | AppleScriptDialogResponse = free_text_response
        elif dialog_result.button is not None:
            response = self.build_permission_response(dialog_result.button, normalized_payload)
        else:
            response = DEFAULT_HOOK_RESPONSE
        return HookProcessingResult(
            display=dialog,
            transport_result=dialog_result.transport,
            response=response,
            error=self.transport_error(dialog_result.transport, current_error),
        )

    def handle_permission_choice(
        self,
        payload: HookPayload,
        transport: DisplayTransport,
        *,
        current_error: str | None = None,
    ) -> tuple[HookProcessingResult | None, str | None]:
        """Show the permission picker and build the response for the chosen scope.

        :param payload: Normalized permission payload.
        :type payload: HookPayload
        :param transport: UI transport implementation.
        :type transport: DisplayTransport
        :param current_error: Existing processing error, if any.
        :type current_error: str | None
        :return: A tuple of the processing result and the error to carry forward. The
            result is ``None`` when the caller should fall back to the standard
            permission dialog; the carried error preserves a picker transport failure
            so it still surfaces in logs after the fallback.
        """
        if not hasattr(transport, "show_permission_choice_dialog"):
            # Custom transports from older versions may not implement the picker; fall
            # back to the standard permission dialog instead of crashing.
            return None, current_error

        dialog = build_permission_choice_dialog(payload)
        dialog_result = transport.show_permission_choice_dialog(dialog)
        if dialog_result.transport.status == TransportStatus.SKIPPED:
            # Unsupported platform / disabled: fall back without recording an error.
            return None, current_error
        if dialog_result.transport.status != TransportStatus.SUCCEEDED:
            # Transport/script failure: fall back to the standard permission dialog
            # instead of denying, but keep the picker error so it is still logged.
            return None, self.transport_error(dialog_result.transport, current_error)

        free_text_response = self._free_text_response(payload, dialog_result.free_text)
        response = free_text_response or build_permission_choice_response(
            payload, dialog_result.choice
        )
        return (
            HookProcessingResult(
                display=dialog,
                transport_result=dialog_result.transport,
                response=response,
                error=self.transport_error(dialog_result.transport, current_error),
            ),
            current_error,
        )

    def handle_ask_user_question(
        self,
        payload: HookPayload,
        transport: DisplayTransport,
        *,
        current_error: str | None = None,
    ) -> tuple[HookProcessingResult | None, str | None]:
        """Show the AskUserQuestion picker and inject collected answers.

        :param payload: Normalized permission payload.
        :type payload: HookPayload
        :param transport: UI transport implementation.
        :type transport: DisplayTransport
        :param current_error: Existing processing error, if any.
        :type current_error: str | None
        :return: A tuple of the processing result and the error to carry forward. The
            result is ``None`` when the caller should fall back to the standard
            permission dialog; the carried error preserves a picker transport failure
            so it still surfaces in logs after the fallback.
        """
        if not hasattr(transport, "show_ask_user_question_dialog"):
            # Custom transports from older versions may not implement the picker; fall
            # back to the standard permission dialog instead of crashing.
            return None, current_error

        dialog = build_ask_user_question_dialog(payload)
        dialog_result = transport.show_ask_user_question_dialog(dialog)
        if dialog_result.transport.status == TransportStatus.SKIPPED:
            # Unsupported platform / disabled: fall back without recording an error.
            return None, current_error
        if dialog_result.transport.status != TransportStatus.SUCCEEDED:
            # Transport/script failure: fall back to the standard permission dialog
            # instead of denying, but keep the picker error so it is still logged.
            return None, self.transport_error(dialog_result.transport, current_error)

        free_text_response = self._free_text_response(
            payload, dialog_result.free_text, answers=dialog_result.answers
        )
        if free_text_response is not None:
            response = free_text_response
        elif dialog_result.answers is None:
            response = build_ask_user_question_cancel_response(payload)
        else:
            response = build_ask_user_question_response(payload, dialog_result.answers)

        return (
            HookProcessingResult(
                display=dialog,
                transport_result=dialog_result.transport,
                response=response,
                error=self.transport_error(dialog_result.transport, current_error),
            ),
            current_error,
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

    def _free_text_response(
        self,
        payload: HookPayload,
        free_text: FreeText | None,
        *,
        answers: dict[str, str] | None = None,
    ) -> HookResponse | None:
        """Build the response for a free-text override, or ``None`` to fall back to normal handling.

        Free-text corrections / notes ride on Claude Code response fields, so they apply only to
        Claude Code requests; other providers fall through to their standard handling. A
        ``deny_correct`` action denies and feeds the text back as a correction; an ``allow_note``
        action allows and attaches the text as additional context.

        :param payload: Normalized hook payload.
        :type payload: HookPayload
        :param free_text: The free-text override the user submitted, if any.
        :type free_text: FreeText | None
        :param answers: AskUserQuestion answers to allow alongside an ``allow_note`` action.
        :type answers: dict[str, str] | None
        :return: The built response, or ``None`` to use normal handling.
        """
        if free_text is None or payload.provider != HookProvider.CLAUDE_CODE:
            return None
        if free_text.action == FREE_TEXT_ALLOW_NOTE:
            return build_allow_with_context_response(payload, answers or {}, free_text.text)
        return build_correction_response(payload, free_text.text)

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
