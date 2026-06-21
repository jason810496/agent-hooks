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


DisplaySpec: TypeAlias = NotificationSpec | DialogSpec


@dataclass(frozen=True)
class AppleScriptResult:
    """Store the result of one AppleScript invocation."""

    status: TransportStatus
    invocation: AppleScriptInvocation
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    skipped_reason: str = ""


@dataclass(frozen=True)
class DialogResult:
    """Store a dialog selection and its transport metadata."""

    button: DialogButton | None
    transport: AppleScriptResult


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

    @property
    def cancelled(self) -> bool:
        """Return whether the user cancelled the dialog."""
        return self.answers is None


__all__ = [
    "AppleScriptResult",
    "AskUserQuestionDialogResult",
    "AskUserQuestionDialogSpec",
    "AskUserQuestionEntry",
    "AskUserQuestionOption",
    "DialogResult",
    "DialogSpec",
    "DisplaySpec",
    "NotificationSpec",
]
