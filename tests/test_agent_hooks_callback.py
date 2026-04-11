from __future__ import annotations

from io import StringIO
from pathlib import Path

from agent_hooks.cli import run_callback
from agent_hooks.config import RuntimeConfig
from agent_hooks.enums import AppleScriptInvocation, DialogButton, TransportStatus
from agent_hooks.models import AppleScriptResult, DialogResult
from agent_hooks.parsing import build_hook_payload, read_hook_input
from agent_hooks.presentation import build_permission_dialog
from agent_hooks.processor import build_permission_response, process_hook


class FakeTransport:
    def __init__(
        self,
        *,
        notification_result: AppleScriptResult | None = None,
        dialog_result: DialogResult | None = None,
    ) -> None:
        self._notification_result = notification_result or AppleScriptResult(
            status=TransportStatus.SUCCEEDED,
            invocation=AppleScriptInvocation.NOTIFICATION,
        )
        self._dialog_result = dialog_result or DialogResult(
            button=DialogButton.ALLOW_ONCE,
            transport=AppleScriptResult(
                status=TransportStatus.SUCCEEDED,
                invocation=AppleScriptInvocation.DIALOG,
                stdout="button returned:Allow Once",
            ),
        )

    def send_notification(self, notification: object) -> AppleScriptResult:
        return self._notification_result

    def show_dialog(self, dialog: object) -> DialogResult:
        return self._dialog_result


class TestReadHookInput:
    def test_invalid_json_returns_parse_error(self) -> None:
        result = read_hook_input(StringIO("{not-json"))

        assert result.parse_error is not None
        assert result.parse_error.startswith("Invalid hook JSON:")


class TestPresentation:
    def test_permission_dialog_includes_session_rule_preview(self) -> None:
        payload = build_hook_payload(
            {
                "hook_event_name": "PermissionRequest",
                "tool_name": "Bash",
                "tool_input": {"command": "git status"},
                "permission_suggestions": [
                    {
                        "id": "suggestion-1",
                        "rules": [{"toolName": "Bash", "ruleContent": "git *"}],
                    }
                ],
            }
        )

        dialog = build_permission_dialog(payload)

        assert dialog.default_button == DialogButton.ALLOW_ONCE
        assert '"Always Allow" adds session rule: Bash(git *)' in dialog.message


class TestPermissionResponse:
    def test_always_allow_scopes_updates_to_session(self) -> None:
        payload = build_hook_payload(
            {
                "hook_event_name": "PermissionRequest",
                "permission_suggestions": [
                    {
                        "id": "suggestion-1",
                        "rules": [{"toolName": "Bash", "ruleContent": "git *"}],
                    }
                ],
            }
        )

        response = build_permission_response(DialogButton.ALWAYS_ALLOW, payload)

        assert response.as_payload() == {
            "suppressOutput": True,
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {
                    "behavior": "allow",
                    "updatedPermissions": [
                        {
                            "id": "suggestion-1",
                            "rules": [{"toolName": "Bash", "ruleContent": "git *"}],
                            "destination": "session",
                        }
                    ],
                },
            },
        }


class TestProcessHook:
    def test_notification_failure_surfaces_transport_error(self) -> None:
        input_data = read_hook_input(
            StringIO(
                '{"hook_event_name":"Stop","last_assistant_message":"Completed successfully."}'
            )
        )
        transport = FakeTransport(
            notification_result=AppleScriptResult(
                status=TransportStatus.FAILED,
                invocation=AppleScriptInvocation.NOTIFICATION,
                returncode=1,
                stderr="notification failed",
            )
        )

        result = process_hook(input_data, transport)

        assert result.error == "notification failed"
        assert result.response.as_payload() == {"suppressOutput": True}


class TestRunCallback:
    def test_run_callback_emits_structured_response(self, tmp_path: Path) -> None:
        stdin = StringIO(
            """
            {
              "hook_event_name": "PermissionRequest",
              "tool_name": "Bash",
              "tool_input": {"command": "git status"}
            }
            """
        )
        stdout = StringIO()
        runtime_config = RuntimeConfig(
            project_root=tmp_path,
            log_path=tmp_path / "logs" / "hooks.log",
            raw_log_path=tmp_path / "logs" / "hooks.raw.log",
            skip_osascript=True,
        )

        exit_code = run_callback(
            stdin=stdin,
            stdout=stdout,
            runtime_config=runtime_config,
            transport=FakeTransport(),
        )

        assert exit_code == 0
        assert (
            stdout.getvalue()
            == '{"suppressOutput":true,"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}\n'
        )
