"""Compatibility imports for the former processing module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_hooks.default_handlers import (
    DEFAULT_HOOK_RESPONSE,
    DefaultHookHandler,
    HookFallbackHandler,
    build_permission_response,
    process_notification_event,
    process_permission_request,
    transport_error,
)
from agent_hooks.enums import HookEventName
from agent_hooks.models.schemas.processing import HookProcessingResult

if TYPE_CHECKING:
    from agent_hooks.models.schemas.hooks import HookInput
    from agent_hooks.transport import DisplayTransport


def process_hook(input_data: HookInput, transport: DisplayTransport) -> HookProcessingResult:
    """Process a parsed hook payload into a response and optional UI action.

    Preserved for backward compatibility with the former ``agent_hooks.processor``
    module. New code should route through ``AgentHook`` and its fallback handler.

    :param input_data: Parsed hook input.
    :type input_data: HookInput
    :param transport: UI transport implementation.
    :type transport: DisplayTransport
    :return: Processing result for logging and emission.
    """
    error = input_data.parse_error
    if error is not None:
        return HookProcessingResult(
            display=None,
            transport_result=None,
            response=DEFAULT_HOOK_RESPONSE,
            error=error,
        )

    payload = input_data.payload
    if payload.event_name == HookEventName.PERMISSION_REQUEST:
        return process_permission_request(payload, transport, current_error=error)
    return process_notification_event(payload, transport, current_error=error)


__all__ = [
    "DEFAULT_HOOK_RESPONSE",
    "DefaultHookHandler",
    "HookFallbackHandler",
    "build_permission_response",
    "process_hook",
    "process_notification_event",
    "process_permission_request",
    "transport_error",
]
