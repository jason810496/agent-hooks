"""Build Claude Code display models."""

from __future__ import annotations

from agent_hooks.enums import DialogButton, HookEventName, NotificationSound
from agent_hooks.models.schemas.display import DialogSpec, NotificationSpec
from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.providers.claude_code.permissions import first_permission_rule
from agent_hooks.providers.common import format_tool_detail
from agent_hooks.text import compact_text, first_non_empty_line, humanize

PROVIDER_DISPLAY_NAME = "Claude Code"
PROVIDER_SHORT_NAME = "Claude"
NOTIFICATION_SOUNDS = {
    "permission_prompt": NotificationSound.PING,
    "idle_prompt": NotificationSound.PING,
    "auth_success": NotificationSound.GLASS,
    "elicitation_dialog": NotificationSound.PING,
}


def build_notification(payload: HookPayload) -> NotificationSpec | None:
    """Build the supported Claude Code notification display."""
    if payload.event_name == HookEventName.NOTIFICATION:
        title = compact_text(
            payload.title or humanize(payload.raw_notification_type) or PROVIDER_DISPLAY_NAME
        )
        message = compact_text(payload.message or f"{PROVIDER_DISPLAY_NAME} sent a notification.")
        return NotificationSpec(
            title=title,
            message=message,
            sound=NOTIFICATION_SOUNDS.get(payload.raw_notification_type, NotificationSound.PING),
        )

    if payload.event_name == HookEventName.STOP:
        return NotificationSpec(
            title=f"{PROVIDER_SHORT_NAME} finished",
            message=compact_text(
                first_non_empty_line(payload.last_assistant_message)
                or f"{PROVIDER_SHORT_NAME} finished responding."
            ),
            sound=NotificationSound.GLASS,
        )

    if payload.event_name == HookEventName.STOP_FAILURE:
        return NotificationSpec(
            title=f"{PROVIDER_SHORT_NAME} error",
            message=compact_text(
                first_non_empty_line(payload.error_details)
                or first_non_empty_line(payload.last_assistant_message)
                or first_non_empty_line(payload.error)
                or f"{PROVIDER_SHORT_NAME} hit an API error."
            ),
            subtitle=compact_text(payload.error),
            sound=NotificationSound.BASSO,
        )

    return None


def build_permission_dialog(payload: HookPayload) -> DialogSpec:
    """Build the Claude Code permission dialog."""
    message = format_tool_detail(payload)
    first_rule = first_permission_rule(payload)
    if first_rule is not None and first_rule.tool_name and first_rule.rule_content:
        message += (
            '\n\n"Always Allow" adds session rule: '
            f"{first_rule.tool_name}({first_rule.rule_content})"
        )

    return DialogSpec(
        title=f"{PROVIDER_DISPLAY_NAME} — Permission Request",
        message=message,
        buttons=(
            DialogButton.DENY,
            DialogButton.ALLOW_ONCE,
            DialogButton.ALWAYS_ALLOW,
        ),
        default_button=DialogButton.ALLOW_ONCE,
    )
