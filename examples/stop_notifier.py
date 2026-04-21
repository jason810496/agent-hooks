"""Send custom notifications for stop and attention events."""

from __future__ import annotations

from example_utils import compact_text

from agent_hooks import (
    AgentHook,
    HookResponse,
    NotificationEvent,
    StopEvent,
    StopFailureEvent,
)
from agent_hooks.enums import NotificationSound
from agent_hooks.models.response import HookProcessingResult, NotificationSpec
from agent_hooks.transport import DisplayTransport

app = AgentHook(fallback_to_default_processor=False)


def send_notification(
    notification: NotificationSpec,
    transport: DisplayTransport,
) -> HookProcessingResult:
    """Send one notification through the injected transport.

    :param notification: Notification specification to deliver.
    :type notification: NotificationSpec
    :param transport: Display transport used by Agent Hooks.
    :type transport: DisplayTransport
    :return: Processing result that preserves the notification metadata.
    """
    transport_result = transport.send_notification(notification)
    return HookProcessingResult(
        display=notification,
        transport_result=transport_result,
        response=HookResponse(),
    )


@app.notification()
def notification_handler(
    hook_event: NotificationEvent,
    transport: DisplayTransport,
) -> HookProcessingResult:
    """Notify when Claude asks for attention.

    :param hook_event: Claude notification event from Agent Hooks.
    :type hook_event: NotificationEvent
    :param transport: Display transport used by Agent Hooks.
    :type transport: DisplayTransport
    :return: Processing result for the notification.
    """
    notification = NotificationSpec(
        title=hook_event.title or "Claude Code needs attention",
        message=compact_text(hook_event.message or "A local callback requires attention."),
        subtitle=hook_event.raw_notification_type or hook_event.provider.value,
        sound=NotificationSound.PING,
    )
    return send_notification(notification, transport)


@app.stop()
def stop_handler(
    hook_event: StopEvent,
    transport: DisplayTransport,
) -> HookProcessingResult:
    """Send a completion notification when an agent stops.

    :param hook_event: Stop event from Agent Hooks.
    :type hook_event: StopEvent
    :param transport: Display transport used by Agent Hooks.
    :type transport: DisplayTransport
    :return: Processing result for the notification.
    """
    notification = NotificationSpec(
        title=f"{hook_event.provider.value} session finished",
        message=compact_text(hook_event.last_assistant_message or "The agent session stopped."),
        subtitle=hook_event.session_id or hook_event.cwd,
        sound=NotificationSound.GLASS,
    )
    return send_notification(notification, transport)


@app.stop_failure()
def stop_failure_handler(
    hook_event: StopFailureEvent,
    transport: DisplayTransport,
) -> HookProcessingResult:
    """Send a stronger notification when Claude stops with an error.

    :param hook_event: Stop-failure event from Agent Hooks.
    :type hook_event: StopFailureEvent
    :param transport: Display transport used by Agent Hooks.
    :type transport: DisplayTransport
    :return: Processing result for the notification.
    """
    notification = NotificationSpec(
        title="Claude Code stopped with an error",
        message=compact_text(
            hook_event.error_details or hook_event.error or hook_event.last_assistant_message
        ),
        subtitle=hook_event.session_id or hook_event.cwd,
        sound=NotificationSound.BASSO,
    )
    return send_notification(notification, transport)
