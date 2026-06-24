"""Provide the built-in callback application.

The ``AgentHook`` instance and default handlers here are UI-agnostic: the display
transport (AppleScript or the SQLite-backed Swift UI) is chosen by the CLI and injected
at runtime through ``run_callback``.
"""

from __future__ import annotations

from agent_hooks.default_handlers import DefaultHookHandler
from agent_hooks.models.events import (
    NotificationEvent,
    PermissionRequestEvent,
    PostToolUseEvent,
    SessionStartEvent,
    StopEvent,
    StopFailureEvent,
    UserPromptSubmitEvent,
)
from agent_hooks.models.response import HookProcessingResult, HookResponse
from agent_hooks.router import AgentHook
from agent_hooks.transport import DisplayTransport

default_handler = DefaultHookHandler()
app = AgentHook(fallback_handler=None)


@app.notification()
def notification_handler(
    hook_event: NotificationEvent,
    transport: DisplayTransport,
) -> HookProcessingResult:
    """Handle built-in notification events."""
    return default_handler.handle_notification_event(hook_event, transport)


@app.permission()
def permission_handler(
    hook_event: PermissionRequestEvent,
    transport: DisplayTransport,
) -> HookProcessingResult:
    """Handle Claude permission requests and Codex pre-tool-use events."""
    return default_handler.handle_permission_request(hook_event, transport)


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
    return default_handler.handle_notification_event(hook_event, transport)


@app.stop_failure()
def stop_failure_handler(
    hook_event: StopFailureEvent,
    transport: DisplayTransport,
) -> HookProcessingResult:
    """Handle built-in failed-stop events."""
    return default_handler.handle_notification_event(hook_event, transport)


__all__ = ["app", "default_handler"]
