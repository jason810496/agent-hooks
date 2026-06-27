"""Define UI-facing display and transport models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from agent_hooks.enums import (
    AppleScriptInvocation,
    DialogButton,
    NotificationSound,
    TransportStatus,
)


@dataclass(frozen=True)
class NotificationSpec:
    """Store a macOS notification request."""

    title: str
    message: str
    subtitle: str = ""
    sound: NotificationSound = NotificationSound.NONE


@dataclass(frozen=True)
class DialogSpec:
    """Store an interactive macOS dialog request."""

    title: str
    message: str
    buttons: tuple[DialogButton, ...]
    default_button: DialogButton
    font_size: int | None = None


@dataclass(frozen=True)
class AppleScriptResult:
    """Store the result of one AppleScript invocation."""

    status: TransportStatus
    invocation: AppleScriptInvocation
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    skipped_reason: str = ""


#: Free-text action: deny the suggested step and feed the user's text back as a correction.
FREE_TEXT_DENY_CORRECT = "deny_correct"
#: Free-text action: allow the suggested step but attach the user's text as extra model context.
FREE_TEXT_ALLOW_NOTE = "allow_note"


@dataclass(frozen=True)
class FreeText:
    """Store a free-text override the user typed instead of (or alongside) a plain choice.

    ``action`` is one of :data:`FREE_TEXT_DENY_CORRECT` or :data:`FREE_TEXT_ALLOW_NOTE`;
    ``text`` is the user's correction / note delivered back to the model.
    """

    action: str
    text: str


@dataclass(frozen=True)
class DialogResult:
    """Store a dialog selection and its transport metadata."""

    button: DialogButton | None
    transport: AppleScriptResult
    free_text: FreeText | None = None


@dataclass(frozen=True)
class AskUserQuestionOption:
    """Store one selectable option for an AskUserQuestion dialog."""

    label: str
    description: str = ""


@dataclass(frozen=True)
class AskUserQuestionEntry:
    """Store one question for an AskUserQuestion dialog."""

    question: str
    header: str
    multi_select: bool
    options: tuple[AskUserQuestionOption, ...]


@dataclass(frozen=True)
class AskUserQuestionDialogSpec:
    """Store an interactive request that collects answers for AskUserQuestion."""

    title: str
    questions: tuple[AskUserQuestionEntry, ...]


@dataclass(frozen=True)
class AskUserQuestionDialogResult:
    """Store answers collected from the AskUserQuestion dialog."""

    answers: dict[str, str] | None
    transport: AppleScriptResult
    free_text: FreeText | None = None

    @property
    def cancelled(self) -> bool:
        """Return whether the user cancelled the dialog."""
        return self.answers is None and self.free_text is None


@dataclass(frozen=True)
class PermissionChoice:
    """Store one selectable choice in the permission picker.

    Each choice maps a list entry to the response it produces. ``suggestion_index``
    points at the permission suggestion (in payload order) that ``ALWAYS_ALLOW``
    choices persist; it is ``None`` for choices that persist nothing, such as the
    leading "Allow once" entry.
    """

    label: str
    button: DialogButton
    suggestion_index: int | None = None


@dataclass(frozen=True)
class PermissionChoiceDialogSpec:
    """Store an interactive permission picker that lists each suggestion as a choice."""

    title: str
    message: str
    choices: tuple[PermissionChoice, ...]
    default_index: int = 0


@dataclass(frozen=True)
class PermissionChoiceDialogResult:
    """Store the choice selected from the permission picker."""

    choice: PermissionChoice | None
    transport: AppleScriptResult
    free_text: FreeText | None = None

    @property
    def cancelled(self) -> bool:
        """Return whether the user dismissed the picker without choosing."""
        return self.choice is None and self.free_text is None


DisplaySpec: TypeAlias = (
    NotificationSpec
    | DialogSpec
    | AskUserQuestionDialogSpec
    | PermissionChoiceDialogSpec
)


__all__ = [
    "FREE_TEXT_ALLOW_NOTE",
    "FREE_TEXT_DENY_CORRECT",
    "AppleScriptResult",
    "AskUserQuestionDialogResult",
    "AskUserQuestionDialogSpec",
    "AskUserQuestionEntry",
    "AskUserQuestionOption",
    "DialogResult",
    "DialogSpec",
    "DisplaySpec",
    "FreeText",
    "NotificationSpec",
    "PermissionChoice",
    "PermissionChoiceDialogResult",
    "PermissionChoiceDialogSpec",
]
