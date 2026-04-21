"""Provide the built-in AppleScript callback application."""

from __future__ import annotations

from agent_hooks.models.response import HookProcessingResult, HookResponse
from agent_hooks.processor import process_notification_event, process_permission_request
from agent_hooks.router import (
    AgentHook,
    NotificationEvent,
    PermissionRequestEvent,
    PostToolUseEvent,
    SessionStartEvent,
    StopEvent,
    StopFailureEvent,
    UserPromptSubmitEvent,
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
    """Handle Claude permission requests and Codex pre-tool-use events."""
    return process_permission_request(hook_event, transport)


@app.session_start()
def session_start_handler(_hook_event: SessionStartEvent) -> HookResponse:
    """Handle built-in Codex session-start events."""
    return HookResponse()


@app.user_prompt_submit()
def user_prompt_submit_handler(_hook_event: UserPromptSubmitEvent) -> HookResponse:
    """Handle built-in Codex user-prompt-submit events."""
    return HookResponse()


@app.post_tool_use()
def post_tool_use_handler(_hook_event: PostToolUseEvent) -> HookResponse:
    """Handle built-in Codex post-tool-use events."""
    return HookResponse()


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
