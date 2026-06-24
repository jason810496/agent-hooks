"""Define the display-transport protocol and a no-op default.

The framework is transport-agnostic: it speaks only to the :class:`DisplayTransport`
protocol and never constructs a concrete UI transport. Apps (see ``src/app``) build the
transport they want -- AppleScript, the SQLite-backed Swift UI, etc. -- and inject it
into :func:`agent_hooks.runner.run_callback`. :class:`NoopDisplayTransport` is the safe
fallback used when no transport is injected, so dispatch never crashes for callers that
do not supply one.
"""

from __future__ import annotations

from typing import Protocol

from agent_hooks.enums import AppleScriptInvocation, TransportStatus
from agent_hooks.models.schemas.display import (
    AppleScriptResult,
    AskUserQuestionDialogResult,
    AskUserQuestionDialogSpec,
    DialogResult,
    DialogSpec,
    NotificationSpec,
    PermissionChoiceDialogResult,
    PermissionChoiceDialogSpec,
)


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

    def show_ask_user_question_dialog(
        self, dialog: AskUserQuestionDialogSpec
    ) -> AskUserQuestionDialogResult:
        """Show a multi-question picker dialog and collect the answers.

        :param dialog: AskUserQuestion dialog specification.
        :type dialog: AskUserQuestionDialogSpec
        :return: Collected answers and transport metadata.
        """
        ...

    def show_permission_choice_dialog(
        self, dialog: PermissionChoiceDialogSpec
    ) -> PermissionChoiceDialogResult:
        """Show the permission picker and capture the selected choice.

        :param dialog: Permission picker specification.
        :type dialog: PermissionChoiceDialogSpec
        :return: Selected choice and transport metadata.
        """
        ...


class NoopDisplayTransport:
    """Skip every display action so dispatch works without an injected transport.

    Every method reports a ``SKIPPED`` transport result, which the default handlers
    treat as "no decision / fall back to the default response" rather than an error.
    """

    def send_notification(self, notification: NotificationSpec) -> AppleScriptResult:
        """Skip the notification and report it as skipped."""
        del notification
        return self._skipped(AppleScriptInvocation.NOTIFICATION)

    def show_dialog(self, dialog: DialogSpec) -> DialogResult:
        """Skip the dialog and return no button selection."""
        del dialog
        return DialogResult(button=None, transport=self._skipped(AppleScriptInvocation.DIALOG))

    def show_ask_user_question_dialog(
        self, dialog: AskUserQuestionDialogSpec
    ) -> AskUserQuestionDialogResult:
        """Skip the AskUserQuestion picker and return no answers."""
        del dialog
        return AskUserQuestionDialogResult(
            answers=None, transport=self._skipped(AppleScriptInvocation.ASK_USER_QUESTION)
        )

    def show_permission_choice_dialog(
        self, dialog: PermissionChoiceDialogSpec
    ) -> PermissionChoiceDialogResult:
        """Skip the permission picker and return no choice."""
        del dialog
        return PermissionChoiceDialogResult(
            choice=None, transport=self._skipped(AppleScriptInvocation.PERMISSION_CHOICE)
        )

    @staticmethod
    def _skipped(invocation: AppleScriptInvocation) -> AppleScriptResult:
        """Build a skipped transport result for one invocation."""
        return AppleScriptResult(
            status=TransportStatus.SKIPPED,
            invocation=invocation,
            skipped_reason="no-transport",
        )


__all__ = ["DisplayTransport", "NoopDisplayTransport"]
