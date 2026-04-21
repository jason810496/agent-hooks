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


__all__ = [
    "AppleScriptResult",
    "DialogResult",
    "DialogSpec",
    "DisplaySpec",
    "NotificationSpec",
]
