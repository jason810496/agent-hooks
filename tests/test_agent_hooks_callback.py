from __future__ import annotations

import json
import logging
from io import StringIO
from pathlib import Path

from agent_hooks.cli import run_callback
from agent_hooks.config import (
    ApplicationLoggingConfig,
    AuditLoggingConfig,
    FileLoggingConfig,
    RuntimeConfig,
    load_runtime_config,
)
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


class TestRuntimeConfig:
    def test_load_runtime_config_reads_environment_overrides(self, tmp_path: Path) -> None:
        env = {
            "AGENT_HOOK_PROJECT_ROOT": str(tmp_path),
            "AGENT_HOOK_LOG_DIR": "var/logs",
            "AGENT_HOOK_DISABLE_OSASCRIPT": "true",
            "AGENT_HOOK_APP_LOG_PATH": "runtime/app.log",
            "AGENT_HOOK_APP_LOG_FORMAT": "%(levelname)s %(message)s",
            "AGENT_HOOK_APP_LOG_LEVEL": "debug",
            "AGENT_HOOK_LOG_MAX_BYTES": "2048",
            "AGENT_HOOK_LOG_BACKUP_COUNT": "6",
            "AGENT_HOOK_RESPONSE_AUDIT_LOG_PATH": "runtime/response.log",
        }

        config = load_runtime_config(env)

        assert config.project_root == tmp_path
        assert config.log_directory == tmp_path / "var" / "logs"
        assert config.skip_osascript is True
        assert config.application_logging.file.path == tmp_path / "runtime" / "app.log"
        assert config.application_logging.level == logging.DEBUG
        assert config.application_logging.level_name == "DEBUG"
        assert config.application_logging.format_string == "%(levelname)s %(message)s"
        assert config.audit_logging.input_file.max_bytes == 2048
        assert config.audit_logging.response_file.backup_count == 6
        assert config.audit_logging.response_file.path == tmp_path / "runtime" / "response.log"


class TestRunCallback:
    def test_run_callback_emits_structured_response_and_writes_logs(
        self,
        tmp_path: Path,
    ) -> None:
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
            log_directory=tmp_path / "logs",
            skip_osascript=True,
            application_logging=ApplicationLoggingConfig(
                file=FileLoggingConfig(
                    path=tmp_path / "logs" / "hooks.log",
                    max_bytes=1024 * 1024,
                    backup_count=1,
                ),
                level=logging.DEBUG,
                level_name="DEBUG",
                format_string="%(levelname)s %(message)s",
            ),
            audit_logging=AuditLoggingConfig(
                input_file=FileLoggingConfig(
                    path=tmp_path / "logs" / "hooks.raw.log",
                    max_bytes=1024 * 1024,
                    backup_count=1,
                ),
                response_file=FileLoggingConfig(
                    path=tmp_path / "logs" / "hooks.response.log",
                    max_bytes=1024 * 1024,
                    backup_count=1,
                ),
            ),
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
        input_audit_record = json.loads(runtime_config.raw_log_path.read_text(encoding="utf-8"))
        assert input_audit_record["hook_event_name"] == "PermissionRequest"
        assert input_audit_record["raw_input"].strip().startswith("{")

        response_audit_record = json.loads(
            runtime_config.response_log_path.read_text(encoding="utf-8")
        )
        assert response_audit_record["hook_event_name"] == "PermissionRequest"
        assert response_audit_record["hook_response"] == stdout.getvalue()

        app_log = runtime_config.log_path.read_text(encoding="utf-8")
        assert app_log.startswith("INFO ")
        assert '"hook_event_name": "PermissionRequest"' in app_log
        expected_response_bytes = len(stdout.getvalue().encode("utf-8"))
        assert f'"response_bytes": {expected_response_bytes}' in app_log
