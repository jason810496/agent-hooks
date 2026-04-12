"""Execute macOS AppleScript actions for notifications and dialogs."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Protocol

from agent_hooks.enums import AppleScriptInvocation, DialogButton, TransportStatus
from agent_hooks.models import AppleScriptResult, DialogResult, DialogSpec, NotificationSpec

NOTIFICATION_SCRIPT = """
on run argv
    set theMessage to item 1 of argv
    set theTitle to item 2 of argv
    set theSubtitle to item 3 of argv
    set theSoundName to item 4 of argv

    if theSubtitle is "" and theSoundName is "" then
        display notification theMessage with title theTitle
    else if theSubtitle is "" then
        display notification theMessage with title theTitle sound name theSoundName
    else if theSoundName is "" then
        display notification theMessage with title theTitle subtitle theSubtitle
    else
        display notification theMessage with title theTitle subtitle theSubtitle sound name theSoundName
    end if
end run
""".strip()

DIALOG_SCRIPT = """
on run argv
    set theMessage to item 1 of argv
    set theTitle to item 2 of argv
    set theDefault to item 3 of argv
    set theIconPath to item 4 of argv
    set buttonList to {}
    repeat with i from 5 to (count of argv)
        set end of buttonList to item i of argv
    end repeat
    if theIconPath is "" then
        display dialog theMessage with title theTitle buttons buttonList default button theDefault with icon caution
    else
        display dialog theMessage with title theTitle buttons buttonList default button theDefault with icon (POSIX file theIconPath)
    end if
end run
""".strip()

OSASCRIPT_LOGO_PATH = Path(__file__).resolve().parent / "assets" / "osascript-logo.png"


def resolve_dialog_icon_path() -> str:
    """Return the packaged dialog icon path when available."""
    if OSASCRIPT_LOGO_PATH.is_file():
        return str(OSASCRIPT_LOGO_PATH)
    return ""


class DisplayTransport(Protocol):
    """Define the transport interface used by the processor."""

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

    def __init__(self, *, skip_osascript: bool) -> None:
        """Initialize the transport configuration.

        :param skip_osascript: Whether AppleScript execution is disabled.
        :type skip_osascript: bool
        """
        self._skip_osascript = skip_osascript
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
            script=NOTIFICATION_SCRIPT,
        )

    def show_dialog(self, dialog: DialogSpec) -> DialogResult:
        """Show a macOS dialog and capture the selected button.

        :param dialog: Dialog specification.
        :type dialog: DialogSpec
        :return: Dialog result with button selection.
        """
        transport = self._run_osascript(
            invocation=AppleScriptInvocation.DIALOG,
            arguments=[
                dialog.message,
                dialog.title,
                dialog.default_button.value,
                resolve_dialog_icon_path(),
                *(button.value for button in dialog.buttons),
            ],
            script=DIALOG_SCRIPT,
        )
        button = (
            parse_dialog_button(transport.stdout)
            if transport.status == TransportStatus.SUCCEEDED
            else None
        )
        return DialogResult(button=button, transport=transport)

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


def parse_dialog_button(stdout: str) -> DialogButton | None:
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
