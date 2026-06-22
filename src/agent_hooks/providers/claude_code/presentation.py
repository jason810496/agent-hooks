"""Build Claude Code display models."""

from __future__ import annotations

from agent_hooks.enums import DialogButton, HookEventName, HookProvider, NotificationSound
from agent_hooks.models.schemas.display import (
    AskUserQuestionDialogSpec,
    AskUserQuestionEntry,
    AskUserQuestionOption,
    DialogSpec,
    NotificationSpec,
    PermissionChoice,
    PermissionChoiceDialogSpec,
)
from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.models.schemas.json_types import JsonObject
from agent_hooks.providers.claude_code.permissions import (
    build_permission_suggestions,
    describe_permission_rule,
    describe_permission_suggestion,
)
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
    """Build the Claude Code permission dialog.

    This three-button dialog is the fallback shown when the interactive picker is
    unavailable (non-macOS hosts, disabled ``osascript``, or a picker failure), so
    its ``Always Allow`` button still applies every offered suggestion. The message
    lists every suggestion rule so the full scope is visible before that button is
    pressed.
    """
    message = format_tool_detail(payload)
    questions_preview = format_ask_user_question_preview(payload)
    if questions_preview:
        message += f"\n\n{questions_preview}"

    suggestions_preview = format_permission_suggestions_preview(payload)
    if suggestions_preview:
        message += f"\n\n{suggestions_preview}"

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


def format_permission_suggestions_preview(payload: HookPayload) -> str:
    """Return a bullet list of every session rule the suggestions would persist.

    :param payload: Normalized permission payload.
    :type payload: HookPayload
    :return: A header line followed by one bullet per rule (or per non-rule
        suggestion), or an empty string when no suggestions are offered.
    """
    lines: list[str] = []
    for suggestion in build_permission_suggestions(payload.raw):
        rule_labels = [
            label
            for label in (describe_permission_rule(rule) for rule in suggestion.rules)
            if label
        ]
        if rule_labels:
            lines.extend(f"  - {label}" for label in rule_labels)
        else:
            # No rules, or rules that all render empty: fall back to the suggestion-level
            # description (mode / directories / id) so the suggestion still appears.
            lines.append(f"  - {describe_permission_suggestion(suggestion)}")
    if not lines:
        return ""
    return '"Always Allow" adds session rules:\n' + "\n".join(lines)


def is_permission_choice_payload(payload: HookPayload) -> bool:
    """Return whether the payload should render the interactive permission picker.

    :param payload: Normalized permission payload.
    :type payload: HookPayload
    :return: ``True`` for Claude permission requests (other than ``AskUserQuestion``)
        that carry at least one permission suggestion to choose from.
    """
    if payload.provider != HookProvider.CLAUDE_CODE:
        return False
    if payload.tool_name == ASK_USER_QUESTION_TOOL_NAME:
        return False
    return bool(build_permission_suggestions(payload.raw))


def build_permission_choice_dialog(payload: HookPayload) -> PermissionChoiceDialogSpec:
    """Build the interactive permission picker that lists each suggestion.

    :param payload: Normalized permission payload.
    :type payload: HookPayload
    :return: A picker whose first choice allows the call once and whose remaining
        choices each persist one suggestion as a session rule.
    """
    choices: list[PermissionChoice] = [
        PermissionChoice(label="Allow once", button=DialogButton.ALLOW_ONCE)
    ]
    # ``choose from list`` returns only the selected label text, and the picker maps
    # that text back to a choice by first match. Identical labels would all resolve to
    # the first occurrence and persist the wrong suggestion, so disambiguate genuine
    # duplicates with a counted suffix while leaving unique labels untouched. The suffix
    # is bumped until the rendered label is unique among labels already used, so a
    # synthetic suffix can never collide with another suggestion's real label.
    used_labels: set[str] = {"Allow once"}
    for index, suggestion in enumerate(build_permission_suggestions(payload.raw)):
        # Show the rule exactly as Claude suggested it. Every entry below "Allow once"
        # is an always-allow choice, so a per-entry "Always allow" prefix is redundant.
        base_label = describe_permission_suggestion(suggestion)
        label = base_label
        suffix = 1
        while label in used_labels:
            suffix += 1
            label = f"{base_label} ({suffix})"
        used_labels.add(label)
        choices.append(
            PermissionChoice(
                label=label,
                button=DialogButton.ALWAYS_ALLOW,
                suggestion_index=index,
            )
        )
    return PermissionChoiceDialogSpec(
        title=f"{PROVIDER_DISPLAY_NAME} — Permission Request",
        message=format_tool_detail(payload),
        choices=tuple(choices),
        default_index=0,
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
