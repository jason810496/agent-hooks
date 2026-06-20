"""Build Claude Code display models."""

from __future__ import annotations

from agent_hooks.enums import DialogButton, HookEventName, HookProvider, NotificationSound
from agent_hooks.models.schemas.display import (
    AskUserQuestionDialogSpec,
    AskUserQuestionEntry,
    AskUserQuestionOption,
    DialogSpec,
    NotificationSpec,
)
from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.models.schemas.json_types import JsonObject
from agent_hooks.providers.claude_code.permissions import first_permission_rule
from agent_hooks.providers.common import (
    coerce_bool,
    coerce_object_list,
    coerce_text,
    format_tool_detail,
)
from agent_hooks.text import compact_text, first_non_empty_line, humanize

PROVIDER_DISPLAY_NAME = "Claude Code"
PROVIDER_SHORT_NAME = "Claude"
ASK_USER_QUESTION_TOOL_NAME = "AskUserQuestion"
ASK_USER_QUESTION_TEXT_LIMIT = 240
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
    questions_preview = format_ask_user_question_preview(payload)
    if questions_preview:
        message += f"\n\n{questions_preview}"

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


def is_ask_user_question_payload(payload: HookPayload) -> bool:
    """Return whether the payload represents an AskUserQuestion permission request."""
    if payload.provider != HookProvider.CLAUDE_CODE:
        return False
    if payload.tool_name != ASK_USER_QUESTION_TOOL_NAME:
        return False
    return bool(coerce_object_list(payload.tool_input.raw.get("questions")))


def build_ask_user_question_dialog(payload: HookPayload) -> AskUserQuestionDialogSpec:
    """Build the interactive AskUserQuestion picker dialog spec."""
    questions = tuple(
        _build_ask_user_question_entry(question_raw)
        for question_raw in coerce_object_list(payload.tool_input.raw.get("questions"))
    )
    return AskUserQuestionDialogSpec(
        title=f"{PROVIDER_DISPLAY_NAME} — Question",
        questions=questions,
    )


def _build_ask_user_question_entry(question_raw: JsonObject) -> AskUserQuestionEntry:
    """Return one normalized AskUserQuestion entry from the raw question payload."""
    options = tuple(
        AskUserQuestionOption(
            label=coerce_text(option_raw.get("label")),
            description=coerce_text(option_raw.get("description")),
        )
        for option_raw in coerce_object_list(question_raw.get("options"))
        if coerce_text(option_raw.get("label"))
    )
    return AskUserQuestionEntry(
        question=coerce_text(question_raw.get("question")),
        header=coerce_text(question_raw.get("header")),
        multi_select=coerce_bool(question_raw.get("multiSelect")),
        options=options,
    )


def format_ask_user_question_preview(payload: HookPayload) -> str:
    """Return a multi-line preview of AskUserQuestion options for the permission dialog."""
    if payload.tool_name != ASK_USER_QUESTION_TOOL_NAME:
        return ""

    questions = coerce_object_list(payload.tool_input.raw.get("questions"))
    if not questions:
        return ""

    blocks: list[str] = []
    for index, question_raw in enumerate(questions, start=1):
        question_text = compact_text(
            coerce_text(question_raw.get("question")),
            limit=ASK_USER_QUESTION_TEXT_LIMIT,
        )
        header = compact_text(coerce_text(question_raw.get("header")), limit=60)
        select_kind = (
            "multi-select" if coerce_bool(question_raw.get("multiSelect")) else "single-select"
        )

        title_parts = [f"Q{index}"]
        if header:
            title_parts.append(f"[{header}]")
        title_parts.append(f"({select_kind})")
        title_line = " ".join(title_parts)
        if question_text:
            title_line = f"{title_line}: {question_text}"

        lines = [title_line]
        for option_raw in coerce_object_list(question_raw.get("options")):
            label = compact_text(coerce_text(option_raw.get("label")), limit=80)
            if not label:
                continue
            description = compact_text(
                coerce_text(option_raw.get("description")),
                limit=ASK_USER_QUESTION_TEXT_LIMIT,
            )
            option_line = f"  - {label}"
            if description:
                option_line += f": {description}"
            lines.append(option_line)
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)
