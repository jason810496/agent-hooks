"""Build display models from normalized payloads."""

from __future__ import annotations

from agent_hooks.enums import (
    DialogButton,
    HookEventName,
    HookProvider,
    NotificationSound,
    NotificationType,
)
from agent_hooks.models import DialogSpec, HookPayload, NotificationSpec, PermissionRule
from agent_hooks.text import compact_text, first_non_empty_line, humanize


def build_notification(payload: HookPayload) -> NotificationSpec | None:
    """Map a normalized payload to a notification, when supported.

    :param payload: Normalized hook payload.
    :type payload: HookPayload
    :return: Notification request, or ``None`` when the event is unsupported.
    """
    if payload.event_name == HookEventName.NOTIFICATION:
        title = compact_text(
            payload.title
            or humanize(payload.raw_notification_type)
            or provider_display_name(payload.provider)
        )
        message = compact_text(
            payload.message or f"{provider_display_name(payload.provider)} sent a notification."
        )
        return NotificationSpec(
            title=title,
            message=message,
            sound=notification_sound_for_type(payload.notification_type),
        )

    if payload.event_name == HookEventName.STOP:
        return NotificationSpec(
            title=f"{provider_short_name(payload.provider)} finished",
            message=compact_text(
                first_non_empty_line(payload.last_assistant_message)
                or f"{provider_short_name(payload.provider)} finished responding."
            ),
            sound=NotificationSound.GLASS,
        )

    if payload.event_name == HookEventName.STOP_FAILURE:
        return NotificationSpec(
            title=f"{provider_short_name(payload.provider)} error",
            message=compact_text(
                first_non_empty_line(payload.error_details)
                or first_non_empty_line(payload.last_assistant_message)
                or first_non_empty_line(payload.error)
                or f"{provider_short_name(payload.provider)} hit an API error."
            ),
            subtitle=compact_text(payload.error),
            sound=NotificationSound.BASSO,
        )

    return None


def build_permission_dialog(payload: HookPayload) -> DialogSpec:
    """Build the permission dialog for a normalized hook payload.

    :param payload: Normalized hook payload.
    :type payload: HookPayload
    :return: Dialog specification for the permission request.
    """
    message = format_tool_detail(payload)
    first_rule = first_permission_rule(payload)
    if first_rule is not None and first_rule.tool_name and first_rule.rule_content:
        message += (
            '\n\n"Always Allow" adds session rule: '
            f"{first_rule.tool_name}({first_rule.rule_content})"
        )

    return DialogSpec(
        title=f"{provider_display_name(payload.provider)} — Permission Request",
        message=message,
        buttons=permission_dialog_buttons(payload.provider),
        default_button=DialogButton.ALLOW_ONCE,
    )


def notification_sound_for_type(notification_type: NotificationType) -> NotificationSound:
    """Return the macOS sound mapped to a notification type.

    :param notification_type: Parsed notification type.
    :type notification_type: NotificationType
    :return: Notification sound.
    """
    sound_by_type = {
        NotificationType.PERMISSION_PROMPT: NotificationSound.PING,
        NotificationType.IDLE_PROMPT: NotificationSound.PING,
        NotificationType.AUTH_SUCCESS: NotificationSound.GLASS,
        NotificationType.ELICITATION_DIALOG: NotificationSound.PING,
    }
    return sound_by_type.get(notification_type, NotificationSound.PING)


def format_tool_detail(payload: HookPayload) -> str:
    """Extract key tool details for dialog display.

    :param payload: Normalized hook payload.
    :type payload: HookPayload
    :return: Multi-line display string.
    """
    tool_input = payload.tool_input
    tool_name = payload.tool_name or "Unknown"
    parts: list[str] = [f"Tool: {tool_name}"]

    if tool_input.command:
        parts.append(f"Command: {compact_text(tool_input.command, limit=400)}")
    if tool_input.file_path:
        parts.append(f"File: {compact_text(tool_input.file_path, limit=400)}")
    if tool_input.description:
        parts.append(f"Description: {compact_text(tool_input.description, limit=300)}")
    if tool_input.url:
        parts.append(f"URL: {compact_text(tool_input.url, limit=400)}")
    if tool_input.query:
        parts.append(f"Query: {compact_text(tool_input.query, limit=300)}")
    if tool_input.prompt and not tool_input.command:
        parts.append(f"Prompt: {compact_text(tool_input.prompt, limit=300)}")
    if tool_input.pattern:
        parts.append(f"Pattern: {compact_text(tool_input.pattern, limit=300)}")

    return "\n".join(parts)


def first_permission_rule(payload: HookPayload) -> PermissionRule | None:
    """Return the first available permission rule preview.

    :param payload: Normalized hook payload.
    :type payload: HookPayload
    :return: First permission rule, or ``None`` when unavailable.
    """
    if not payload.permission_suggestions:
        return None
    first_suggestion = payload.permission_suggestions[0]
    if not first_suggestion.rules:
        return None
    return first_suggestion.rules[0]


def provider_display_name(provider: HookProvider) -> str:
    """Return the user-facing provider label."""
    if provider == HookProvider.CODEX:
        return "Codex"
    return "Claude Code"


def provider_short_name(provider: HookProvider) -> str:
    """Return the short provider label used in notifications."""
    if provider == HookProvider.CODEX:
        return "Codex"
    return "Claude"


def permission_dialog_buttons(provider: HookProvider) -> tuple[DialogButton, ...]:
    """Return the supported permission dialog buttons for one provider."""
    if provider == HookProvider.CODEX:
        return (DialogButton.DENY, DialogButton.ALLOW_ONCE)
    return (
        DialogButton.DENY,
        DialogButton.ALLOW_ONCE,
        DialogButton.ALWAYS_ALLOW,
    )
