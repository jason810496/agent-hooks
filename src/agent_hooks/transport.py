"""Execute macOS AppleScript actions for notifications and dialogs."""

from __future__ import annotations

import shutil
import subprocess
import sys
from functools import cache
from pathlib import Path
from typing import Final, Protocol

from agent_hooks.config import DEFAULT_DIALOG_FONT_SIZE
from agent_hooks.enums import AppleScriptInvocation, DialogButton, TransportStatus
from agent_hooks.models.schemas.display import (
    AppleScriptResult,
    DialogResult,
    DialogSpec,
    NotificationSpec,
)

ASSETS_PATH: Final = Path(__file__).resolve().parent / "assets"
NOTIFICATION_SCRIPT_PATH: Final = ASSETS_PATH / "notification.applescript"
DIALOG_SCRIPT_PATH: Final = ASSETS_PATH / "dialog.applescript"
OSASCRIPT_LOGO_PATH: Final = ASSETS_PATH / "osascript-logo.png"


def _read_applescript(path: Path) -> str:
    """Return AppleScript source from a packaged script file."""
    return path.read_text(encoding="utf-8").strip()


@cache
def get_notification_script() -> str:
    """Return the cached packaged notification AppleScript source."""
    return _read_applescript(NOTIFICATION_SCRIPT_PATH)


@cache
def get_dialog_script() -> str:
    """Return the cached packaged dialog AppleScript source."""
    return _read_applescript(DIALOG_SCRIPT_PATH)


def __getattr__(name: str) -> str:
    """Return lazily loaded script source for legacy module constants."""
    if name == "NOTIFICATION_SCRIPT":
        return get_notification_script()
    if name == "DIALOG_SCRIPT":
        return get_dialog_script()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def resolve_dialog_icon_path() -> str:
    """Return the packaged dialog icon path when available."""
    if OSASCRIPT_LOGO_PATH.is_file():
        return str(OSASCRIPT_LOGO_PATH)
    return ""


class DisplayTransport(Protocol):
    """Define the transport interface used by fallback handlers."""

    def send_notification(self, notification: NotificationSpec) -> AppleScriptResult:
        """Send a notification to the local UI layer.

        :param notification: Notification specification.
        :type notification: NotificationSpec
        :return: Transport result.
        """
        ...

    def show_dialog(self, dialog: DialogSpec) -> DialogResult:
        """Show an interactive permission dialog.

        :param dialog: Dialog specification.
        :type dialog: DialogSpec
        :return: Dialog result with button selection.
        """
        ...


class AppleScriptTransport:
    """Execute AppleScript through the local ``osascript`` binary."""

    def __init__(
        self,
        *,
        skip_osascript: bool,
        dialog_font_size: int = DEFAULT_DIALOG_FONT_SIZE,
    ) -> None:
        """Initialize the transport configuration.

        :param skip_osascript: Whether AppleScript execution is disabled.
        :type skip_osascript: bool
        :param dialog_font_size: Dialog font size in points.
        :type dialog_font_size: int
        """
        self._skip_osascript = skip_osascript
        self._dialog_font_size = dialog_font_size
        self._binary = shutil.which("osascript")

    def send_notification(self, notification: NotificationSpec) -> AppleScriptResult:
        """Send a macOS notification.

        :param notification: Notification specification.
        :type notification: NotificationSpec
        :return: Transport result.
        """
        return self._run_osascript(
            invocation=AppleScriptInvocation.NOTIFICATION,
            arguments=[
                notification.message,
                notification.title,
                notification.subtitle,
                notification.sound.value,
            ],
            script=get_notification_script(),
        )

    def show_dialog(self, dialog: DialogSpec) -> DialogResult:
        """Show a macOS dialog and capture the selected button.

        :param dialog: Dialog specification.
        :type dialog: DialogSpec
        :return: Dialog result with button selection.
        """
        dialog_font_size = self._resolve_dialog_font_size(dialog)
        transport = self._run_osascript(
            invocation=AppleScriptInvocation.DIALOG,
            arguments=[
                dialog.message,
                dialog.title,
                dialog.default_button.value,
                resolve_dialog_icon_path(),
                str(dialog_font_size),
                *(button.value for button in dialog.buttons),
            ],
            script=get_dialog_script(),
        )
        button = (
            self._parse_dialog_button(transport.stdout)
            if transport.status == TransportStatus.SUCCEEDED
            else None
        )
        return DialogResult(button=button, transport=transport)

    def _resolve_dialog_font_size(self, dialog: DialogSpec) -> int:
        """Return the effective positive dialog font size.

        :param dialog: Dialog specification.
        :type dialog: DialogSpec
        :return: Configured positive font size.
        """
        font_size = dialog.font_size if dialog.font_size is not None else self._dialog_font_size
        if font_size <= 0:
            return DEFAULT_DIALOG_FONT_SIZE
        return font_size

    def _run_osascript(
        self,
        *,
        invocation: AppleScriptInvocation,
        arguments: list[str],
        script: str,
    ) -> AppleScriptResult:
        """Execute one AppleScript payload.

        :param invocation: Invocation type.
        :type invocation: AppleScriptInvocation
        :param arguments: Arguments passed to ``osascript``.
        :type arguments: list[str]
        :param script: AppleScript source code.
        :type script: str
        :return: Transport result.
        """
        skipped = self._build_skip_result(invocation)
        if skipped is not None:
            return skipped

        assert self._binary is not None
        try:
            completed = subprocess.run(
                [self._binary, "-e", script, *arguments],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            return AppleScriptResult(
                status=TransportStatus.FAILED,
                invocation=invocation,
                stderr=f"{type(exc).__name__}: {exc}",
            )

        status = TransportStatus.SUCCEEDED if completed.returncode == 0 else TransportStatus.FAILED
        return AppleScriptResult(
            status=status,
            invocation=invocation,
            returncode=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
        )

    def _build_skip_result(self, invocation: AppleScriptInvocation) -> AppleScriptResult | None:
        """Return a skip result when AppleScript execution is unavailable.

        :param invocation: Invocation type.
        :type invocation: AppleScriptInvocation
        :return: Skip result, or ``None`` when execution should proceed.
        """
        if self._skip_osascript:
            return AppleScriptResult(
                status=TransportStatus.SKIPPED,
                invocation=invocation,
                skipped_reason="disabled-by-env",
            )

        if sys.platform != "darwin":
            return AppleScriptResult(
                status=TransportStatus.SKIPPED,
                invocation=invocation,
                skipped_reason="unsupported-platform",
            )

        if self._binary is None:
            return AppleScriptResult(
                status=TransportStatus.SKIPPED,
                invocation=invocation,
                skipped_reason="osascript-not-found",
            )

        return None

    def _parse_dialog_button(self, stdout: str) -> DialogButton | None:
        """Parse the selected button from AppleScript stdout.

        :param stdout: Raw AppleScript stdout.
        :type stdout: str
        :return: Parsed dialog button, or ``None`` when unavailable.
        """
        marker = "button returned:"
        if marker not in stdout:
            return None

        button_label = stdout.split(marker, 1)[1].split(",", 1)[0].splitlines()[0].strip()
        try:
            return DialogButton(button_label)
        except ValueError:
            return None
