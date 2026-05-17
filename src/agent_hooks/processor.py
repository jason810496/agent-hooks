"""Compatibility imports for the former processing module."""

from __future__ import annotations

from agent_hooks.default_handlers import (
    DEFAULT_HOOK_RESPONSE,
    DefaultHookHandler,
    HookFallbackHandler,
    build_permission_response,
    process_notification_event,
    process_permission_request,
    transport_error,
)

__all__ = [
    "DEFAULT_HOOK_RESPONSE",
    "DefaultHookHandler",
    "HookFallbackHandler",
    "build_permission_response",
    "process_notification_event",
    "process_permission_request",
    "transport_error",
]
