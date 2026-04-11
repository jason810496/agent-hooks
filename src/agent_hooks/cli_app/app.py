"""Provide the built-in AppleScript callback application."""

from __future__ import annotations

from agent_hooks.models import HookProcessingResult
from agent_hooks.processor import process_notification_event, process_permission_request
from agent_hooks.router import (
    AgentHook,
    NotificationEvent,
    PermissionRequestEvent,
    StopEvent,
    StopFailureEvent,
)
from agent_hooks.transport import DisplayTransport

app = AgentHook(fallback_to_default_processor=False)


@app.notification()
def notification_handler(
    hook_event: NotificationEvent,
    transport: DisplayTransport,
) -> HookProcessingResult:
    """Handle built-in notification events."""
    return process_notification_event(hook_event, transport)


@app.permission()
def permission_handler(
    hook_event: PermissionRequestEvent,
    transport: DisplayTransport,
) -> HookProcessingResult:
    """Handle built-in permission request events."""
    return process_permission_request(hook_event, transport)


@app.stop()
def stop_handler(
    hook_event: StopEvent,
    transport: DisplayTransport,
) -> HookProcessingResult:
    """Handle built-in stop events."""
    return process_notification_event(hook_event, transport)


@app.stop_failure()
def stop_failure_handler(
    hook_event: StopFailureEvent,
    transport: DisplayTransport,
) -> HookProcessingResult:
    """Handle built-in failed-stop events."""
    return process_notification_event(hook_event, transport)


__all__ = ["app"]
