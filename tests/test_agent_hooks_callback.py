from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from dataclasses import fields
from io import StringIO
from pathlib import Path

import pytest

import agent_hooks.runner as runner_module
from agent_hooks import (
    AgentHook,
    CallbackRequest,
    DefaultHookHandler,
    Depends,
    NotificationEvent,
    PermissionRequestEvent,
    PostToolUseEvent,
    SessionStartEvent,
    StopEvent,
    StopFailureEvent,
    UserPromptSubmitEvent,
)
from agent_hooks.cli_app.app import app
from agent_hooks.cli_app.cli import main as cli_main
from agent_hooks.config import (
    DEFAULT_COMMAND_PREVIEW_MAX_LINE_CHARS,
    DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_CHARS,
    DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_LINES,
    DEFAULT_DIALOG_FONT_SIZE,
    DEFAULT_NOTIFICATION_TIMEOUT_SECONDS,
    ApplicationLoggingConfig,
    AuditLoggingConfig,
    FileLoggingConfig,
    RuntimeConfig,
    load_runtime_config,
)
from agent_hooks.default_handlers import (
    build_permission_response,
    process_permission_request,
)
from agent_hooks.enums import (
    AppleScriptInvocation,
    DialogButton,
    HookControlDecision,
    HookEventName,
    HookProvider,
    TransportStatus,
)
from agent_hooks.models.response import (
    AppleScriptDialogResponse,
    AppleScriptResult,
    DialogResult,
    DialogSpec,
    HookProcessingResult,
    HookResponse,
)
from agent_hooks.models.schemas.display import (
    AskUserQuestionDialogResult,
    AskUserQuestionDialogSpec,
)
from agent_hooks.models.schemas.hooks import HookPayload, ToolInput
from agent_hooks.parsing import build_hook_payload, read_hook_input
from agent_hooks.providers import provider_client
from agent_hooks.providers.claude_code.presentation import is_ask_user_question_payload
from agent_hooks.providers.codex.middleware import (
    CODEX_EXECPOLICY_RULES_ENV_VAR,
    run_codex_execpolicy_check,
)
from agent_hooks.providers.common import format_command_detail
from agent_hooks.runner import run_callback
from agent_hooks.transport import DisplayTransport


class FakeTransport:
    def __init__(
        self,
        *,
        notification_result: AppleScriptResult | None = None,
        dialog_result: DialogResult | None = None,
        ask_user_question_result: AskUserQuestionDialogResult | None = None,
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
        self._ask_user_question_result = ask_user_question_result or AskUserQuestionDialogResult(
            answers=None,
            transport=AppleScriptResult(
                status=TransportStatus.SKIPPED,
                invocation=AppleScriptInvocation.ASK_USER_QUESTION,
                skipped_reason="not-configured",
            ),
        )
        self.notification_calls = 0
        self.dialog_calls = 0
        self.ask_user_question_calls = 0
        self.dialogs: list[object] = []
        self.ask_user_question_dialogs: list[object] = []

    def send_notification(self, notification: object) -> AppleScriptResult:
        self.notification_calls += 1
        return self._notification_result

    def show_dialog(self, dialog: object) -> DialogResult:
        self.dialog_calls += 1
        self.dialogs.append(dialog)
        return self._dialog_result

    def show_ask_user_question_dialog(self, dialog: object) -> AskUserQuestionDialogResult:
        self.ask_user_question_calls += 1
        self.ask_user_question_dialogs.append(dialog)
        return self._ask_user_question_result


def build_runtime_config(
    tmp_path: Path,
    *,
    provider: HookProvider = HookProvider.CLAUDE_CODE,
    dialog_font_size: int = DEFAULT_DIALOG_FONT_SIZE,
    command_preview_max_total_chars: int = DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_CHARS,
    command_preview_max_total_lines: int = DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_LINES,
    command_preview_max_line_chars: int = DEFAULT_COMMAND_PREVIEW_MAX_LINE_CHARS,
    notification_timeout_seconds: float = DEFAULT_NOTIFICATION_TIMEOUT_SECONDS,
) -> RuntimeConfig:
    return RuntimeConfig(
        project_root=tmp_path,
        log_directory=tmp_path / "logs",
        provider=provider,
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
        dialog_font_size=dialog_font_size,
        command_preview_max_total_chars=command_preview_max_total_chars,
        command_preview_max_total_lines=command_preview_max_total_lines,
        command_preview_max_line_chars=command_preview_max_line_chars,
        notification_timeout_seconds=notification_timeout_seconds,
    )


def write_app_module(
    module_path: Path,
    *,
    variable_name: str = "app",
    extra_body: str = "",
) -> None:
    module_path.write_text(
        "\n".join(
            line
            for line in (
                "from __future__ import annotations",
                "",
                "from agent_hooks import AgentHook",
                "",
                f"{variable_name} = AgentHook(fallback_handler=None)",
                extra_body,
                "",
            )
            if line != ""
        )
        + "\n",
        encoding="utf-8",
    )


class TestModelPublicModules:
    def test_request_response_modules_share_schema_classes(self) -> None:
        from agent_hooks.models import HookInput as PackageHookInput
        from agent_hooks.models import HookResponse as PackageHookResponse
        from agent_hooks.models.request import HookInput
        from agent_hooks.models.response import HookResponse
        from agent_hooks.models.schemas.hooks import HookInput as SchemaHookInput
        from agent_hooks.models.schemas.responses import HookResponse as SchemaHookResponse

        assert HookInput is SchemaHookInput
        assert PackageHookInput is SchemaHookInput
        assert HookResponse is SchemaHookResponse
        assert PackageHookResponse is SchemaHookResponse


class TestProcessorCompatModule:
    def test_former_processor_symbols_are_importable(self) -> None:
        from agent_hooks import processor
        from agent_hooks.default_handlers import (
            process_notification_event as handler_process_notification_event,
        )
        from agent_hooks.default_handlers import (
            process_permission_request as handler_process_permission_request,
        )

        assert callable(processor.process_hook)
        assert processor.process_permission_request is handler_process_permission_request
        assert processor.process_notification_event is handler_process_notification_event
        assert "process_hook" in processor.__all__

    def test_process_hook_returns_default_response_on_parse_error(self) -> None:
        from agent_hooks.processor import DEFAULT_HOOK_RESPONSE, process_hook

        result = process_hook(read_hook_input(StringIO("{not-json")), FakeTransport())

        assert result.error is not None
        assert result.display is None
        assert result.transport_result is None
        assert result.response is DEFAULT_HOOK_RESPONSE

    def test_process_hook_dispatches_permission_request_to_dialog(self) -> None:
        from agent_hooks.processor import process_hook

        payload_json = json.dumps(
            {
                "hook_event_name": "PermissionRequest",
                "tool_name": "Bash",
                "tool_input": {"command": "git status"},
            }
        )
        transport = FakeTransport()

        result = process_hook(read_hook_input(StringIO(payload_json)), transport)

        assert transport.dialog_calls == 1
        assert result.error is None
        direct = process_permission_request(
            read_hook_input(StringIO(payload_json)).payload, FakeTransport()
        )
        assert result.response.as_payload() == direct.response.as_payload()


class TestReadHookInput:
    def test_invalid_json_returns_parse_error(self) -> None:
        result = read_hook_input(StringIO("{not-json"))

        assert result.parse_error is not None
        assert result.parse_error.startswith("Invalid hook JSON:")

    def test_codex_provider_normalizes_pre_tool_use_payload(self) -> None:
        result = read_hook_input(
            StringIO(
                """
                {
                  "hook_event_name": "PreToolUse",
                  "cwd": "/tmp/project",
                  "model": "gpt-5.4",
                  "permission_mode": "default",
                  "session_id": "session-1",
                  "tool_input": {"command": "git status"},
                  "tool_name": "Bash",
                  "tool_use_id": "tool-1",
                  "transcript_path": null,
                  "turn_id": "turn-1"
                }
                """
            ),
            provider=HookProvider.CODEX,
        )

        assert result.parse_error is None
        assert result.payload.provider == HookProvider.CODEX
        assert result.payload.event_name.value == "PermissionRequest"
        assert result.payload.raw_event_name == "PreToolUse"
        assert result.payload.tool_input.command == "git status"
        assert result.payload.model == "gpt-5.4"
        assert result.payload.raw["turn_id"] == "turn-1"


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

        dialog = provider_client.build_permission_dialog(payload)

        assert dialog.default_button == DialogButton.ALLOW_ONCE
        assert '"Always Allow" adds session rule: Bash(git *)' in dialog.message

    def test_codex_permission_dialog_uses_two_buttons(self) -> None:
        payload = build_hook_payload(
            {
                "hook_event_name": "PreToolUse",
                "cwd": "/tmp/project",
                "model": "gpt-5.4",
                "permission_mode": "default",
                "session_id": "session-1",
                "tool_input": {"command": "git status"},
                "tool_name": "Bash",
                "tool_use_id": "tool-1",
                "transcript_path": None,
                "turn_id": "turn-1",
            },
            provider=HookProvider.CODEX,
        )

        dialog = provider_client.build_permission_dialog(payload)

        assert dialog.title == "Codex — Permission Request"
        assert dialog.buttons == (DialogButton.DENY, DialogButton.ALLOW_ONCE)

    def test_permission_dialog_preserves_multiline_command_formatting(self) -> None:
        payload = build_hook_payload(
            {
                "hook_event_name": "PreToolUse",
                "cwd": "/tmp/project",
                "model": "gpt-5.4",
                "permission_mode": "default",
                "session_id": "session-1",
                "tool_input": {
                    "command": "python3 - <<'PY'\nimport subprocess\nprint('ok')\nPY",
                },
                "tool_name": "Bash",
                "tool_use_id": "tool-1",
                "transcript_path": None,
                "turn_id": "turn-1",
            },
            provider=HookProvider.CODEX,
        )

        dialog = provider_client.build_permission_dialog(payload)

        assert dialog.message == (
            "Tool: Bash\nCommand:\npython3 - <<'PY'\nimport subprocess\nprint('ok')\nPY"
        )

    def test_permission_dialog_limits_single_line_command_width(self) -> None:
        assert (
            format_command_detail("abcdefghijklmnopqrstuvwxyz", max_line_chars=8)
            == "Command: abcdefg…"
        )

    def test_permission_dialog_previews_ask_user_question_options(self) -> None:
        payload = build_hook_payload(
            {
                "hook_event_name": "PermissionRequest",
                "tool_name": "AskUserQuestion",
                "tool_input": {
                    "questions": [
                        {
                            "question": "Which testing framework would you prefer?",
                            "header": "Testing",
                            "multiSelect": False,
                            "options": [
                                {"label": "Jest", "description": "Fast, snapshot testing"},
                                {"label": "Vitest", "description": "Vite-native, ESM support"},
                            ],
                        },
                        {
                            "question": "Which deployment platforms?",
                            "header": "Deployment",
                            "multiSelect": True,
                            "options": [
                                {"label": "AWS", "description": "Extensive ecosystem"},
                                {"label": "GCP"},
                            ],
                        },
                    ]
                },
            }
        )

        dialog = provider_client.build_permission_dialog(payload)

        assert dialog.message == (
            "Tool: AskUserQuestion\n"
            "\n"
            "Q1 [Testing] (single-select): Which testing framework would you prefer?\n"
            "  - Jest: Fast, snapshot testing\n"
            "  - Vitest: Vite-native, ESM support\n"
            "\n"
            "Q2 [Deployment] (multi-select): Which deployment platforms?\n"
            "  - AWS: Extensive ecosystem\n"
            "  - GCP"
        )

    def test_permission_dialog_skips_question_preview_for_other_tools(self) -> None:
        payload = build_hook_payload(
            {
                "hook_event_name": "PermissionRequest",
                "tool_name": "Bash",
                "tool_input": {
                    "command": "git status",
                    "questions": [{"question": "ignored", "options": []}],
                },
            }
        )

        dialog = provider_client.build_permission_dialog(payload)

        assert "Q1" not in dialog.message

    def test_permission_dialog_ignores_empty_ask_user_question_payload(self) -> None:
        payload = build_hook_payload(
            {
                "hook_event_name": "PermissionRequest",
                "tool_name": "AskUserQuestion",
                "tool_input": {"questions": []},
            }
        )

        dialog = provider_client.build_permission_dialog(payload)

        assert dialog.message == "Tool: AskUserQuestion"


class TestAskUserQuestionFlow:
    def _payload(self) -> HookPayload:
        return build_hook_payload(
            {
                "hook_event_name": "PermissionRequest",
                "tool_name": "AskUserQuestion",
                "tool_input": {
                    "questions": [
                        {
                            "question": "Pick a framework",
                            "header": "Testing",
                            "multiSelect": False,
                            "options": [
                                {"label": "Jest", "description": "Fast"},
                                {"label": "Vitest", "description": "Modern"},
                            ],
                        },
                        {
                            "question": "Pick deployments",
                            "header": "Deploy",
                            "multiSelect": True,
                            "options": [
                                {"label": "AWS"},
                                {"label": "GCP"},
                            ],
                        },
                    ]
                },
            }
        )

    def test_handle_ask_user_question_injects_answers_into_updated_input(self) -> None:
        payload = self._payload()
        transport = FakeTransport(
            ask_user_question_result=AskUserQuestionDialogResult(
                answers={
                    "Pick a framework": "Jest",
                    "Pick deployments": "AWS, GCP",
                },
                transport=AppleScriptResult(
                    status=TransportStatus.SUCCEEDED,
                    invocation=AppleScriptInvocation.ASK_USER_QUESTION,
                ),
            ),
        )

        result = process_permission_request(payload, transport)

        assert transport.ask_user_question_calls == 1
        assert transport.dialog_calls == 0
        assert isinstance(transport.ask_user_question_dialogs[0], AskUserQuestionDialogSpec)
        hook_output = result.response.as_payload()["hookSpecificOutput"]
        decision = hook_output["decision"]
        assert decision["behavior"] == "allow"
        assert decision["updatedInput"]["answers"] == {
            "Pick a framework": "Jest",
            "Pick deployments": "AWS, GCP",
        }
        assert decision["updatedInput"]["questions"] == (payload.tool_input.raw["questions"])
        assert "updatedInput" not in hook_output

    def test_handle_ask_user_question_cancel_returns_deny(self) -> None:
        payload = self._payload()
        transport = FakeTransport(
            ask_user_question_result=AskUserQuestionDialogResult(
                answers=None,
                transport=AppleScriptResult(
                    status=TransportStatus.SUCCEEDED,
                    invocation=AppleScriptInvocation.ASK_USER_QUESTION,
                    stdout="CANCELLED",
                ),
            ),
        )

        result = process_permission_request(payload, transport)

        hook_output = result.response.as_payload()["hookSpecificOutput"]
        assert hook_output["decision"] == {
            "behavior": "deny",
            "message": "Cancelled by local user.",
        }

    def test_pretool_use_ask_user_question_renders_pretool_use_wire_shape(self) -> None:
        from agent_hooks.providers.claude_code.payload import (
            build_hook_payload as build_claude_payload,
        )
        from agent_hooks.providers.claude_code.response import render_response_payload

        raw_payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "AskUserQuestion",
            "tool_input": {
                "questions": [
                    {
                        "question": "Pick one",
                        "header": "Pick",
                        "multiSelect": False,
                        "options": [{"label": "A"}],
                    }
                ]
            },
        }
        input_payload = build_claude_payload(raw_payload)
        assert input_payload.event_name.value == "PermissionRequest"
        assert input_payload.raw_event_name == "PreToolUse"

        transport = FakeTransport(
            ask_user_question_result=AskUserQuestionDialogResult(
                answers={"Pick one": "A"},
                transport=AppleScriptResult(
                    status=TransportStatus.SUCCEEDED,
                    invocation=AppleScriptInvocation.ASK_USER_QUESTION,
                ),
            ),
        )

        result = process_permission_request(input_payload, transport)
        rendered = render_response_payload(
            result.response.as_payload(),
            input_payload=input_payload,
        )

        hook_output = rendered["hookSpecificOutput"]
        assert hook_output["hookEventName"] == "PreToolUse"
        assert hook_output["permissionDecision"] == "allow"
        assert hook_output["updatedInput"]["answers"] == {"Pick one": "A"}
        assert "decision" not in hook_output

    def test_handle_ask_user_question_falls_back_when_transport_skipped(self) -> None:
        payload = self._payload()
        transport = FakeTransport(
            ask_user_question_result=AskUserQuestionDialogResult(
                answers=None,
                transport=AppleScriptResult(
                    status=TransportStatus.SKIPPED,
                    invocation=AppleScriptInvocation.ASK_USER_QUESTION,
                    skipped_reason="unsupported-platform",
                ),
            ),
        )

        result = process_permission_request(payload, transport)

        assert transport.ask_user_question_calls == 1
        assert transport.dialog_calls == 1
        assert isinstance(result.display, DialogSpec)

    def test_handle_ask_user_question_falls_back_when_transport_failed(self) -> None:
        payload = self._payload()
        transport = FakeTransport(
            ask_user_question_result=AskUserQuestionDialogResult(
                answers=None,
                transport=AppleScriptResult(
                    status=TransportStatus.FAILED,
                    invocation=AppleScriptInvocation.ASK_USER_QUESTION,
                    stderr="ERROR:-1:boom",
                ),
            ),
        )

        result = process_permission_request(payload, transport)

        # A transport failure must not be treated as a user cancellation/deny; it should
        # fall back to the standard permission dialog while preserving the picker error
        # so it still surfaces in the application log.
        assert transport.ask_user_question_calls == 1
        assert transport.dialog_calls == 1
        assert isinstance(result.display, DialogSpec)
        assert result.error == "ERROR:-1:boom"

    def test_handle_ask_user_question_falls_back_when_transport_lacks_picker(self) -> None:
        class PickerlessTransport:
            def __init__(self) -> None:
                self.dialog_calls = 0

            def send_notification(self, notification: object) -> AppleScriptResult:
                return AppleScriptResult(
                    status=TransportStatus.SUCCEEDED,
                    invocation=AppleScriptInvocation.NOTIFICATION,
                )

            def show_dialog(self, dialog: object) -> DialogResult:
                self.dialog_calls += 1
                return DialogResult(
                    button=DialogButton.ALLOW_ONCE,
                    transport=AppleScriptResult(
                        status=TransportStatus.SUCCEEDED,
                        invocation=AppleScriptInvocation.DIALOG,
                        stdout="button returned:Allow Once",
                    ),
                )

        payload = self._payload()
        transport = PickerlessTransport()

        result = process_permission_request(payload, transport)

        # A custom transport without the picker method must fall back, not crash.
        assert transport.dialog_calls == 1
        assert isinstance(result.display, DialogSpec)

    def test_is_ask_user_question_payload_requires_claude_provider(self) -> None:
        raw = {
            "tool_name": "AskUserQuestion",
            "tool_input": {"questions": [{"question": "Pick one", "options": [{"label": "A"}]}]},
        }
        claude_payload = HookPayload(
            provider=HookProvider.CLAUDE_CODE,
            tool_name="AskUserQuestion",
            tool_input=ToolInput(raw=raw["tool_input"]),
        )
        codex_payload = HookPayload(
            provider=HookProvider.CODEX,
            tool_name="AskUserQuestion",
            tool_input=ToolInput(raw=raw["tool_input"]),
        )

        assert is_ask_user_question_payload(claude_payload) is True
        assert is_ask_user_question_payload(codex_payload) is False


class TestPermissionResponse:
    def test_build_permission_response_returns_response_model(self) -> None:
        payload = build_hook_payload({"hook_event_name": "PermissionRequest"})

        response = build_permission_response(DialogButton.ALLOW_ONCE, payload)

        assert isinstance(response, AppleScriptDialogResponse)

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

    def test_codex_denied_permission_renders_pre_tool_use_block(self) -> None:
        payload = build_hook_payload(
            {
                "hook_event_name": "PreToolUse",
                "cwd": "/tmp/project",
                "model": "gpt-5.4",
                "permission_mode": "default",
                "session_id": "session-1",
                "tool_input": {"command": "git status"},
                "tool_name": "Bash",
                "tool_use_id": "tool-1",
                "transcript_path": None,
                "turn_id": "turn-1",
            },
            provider=HookProvider.CODEX,
        )

        response = build_permission_response(DialogButton.DENY, payload)

        assert json.loads(
            runner_module._render_hook_response(
                response,
                provider=HookProvider.CODEX,
                input_payload=payload,
            )
        ) == {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Permission denied by local user.",
            },
        }

    def test_codex_allow_once_renders_empty_pre_tool_use_response(self) -> None:
        payload = build_hook_payload(
            {
                "hook_event_name": "PreToolUse",
                "cwd": "/tmp/project",
                "model": "gpt-5.4",
                "permission_mode": "default",
                "session_id": "session-1",
                "tool_input": {"command": "git status"},
                "tool_name": "Bash",
                "tool_use_id": "tool-1",
                "transcript_path": None,
                "turn_id": "turn-1",
            },
            provider=HookProvider.CODEX,
        )

        response = build_permission_response(DialogButton.ALLOW_ONCE, payload)

        assert (
            json.loads(
                runner_module._render_hook_response(
                    response,
                    provider=HookProvider.CODEX,
                    input_payload=payload,
                )
            )
            == {}
        )

    def test_codex_always_allow_falls_back_to_empty_pre_tool_use_response(self) -> None:
        payload = build_hook_payload(
            {
                "hook_event_name": "PreToolUse",
                "cwd": "/tmp/project",
                "model": "gpt-5.4",
                "permission_mode": "default",
                "session_id": "session-1",
                "tool_input": {"command": "git status"},
                "tool_name": "Bash",
                "tool_use_id": "tool-1",
                "transcript_path": None,
                "turn_id": "turn-1",
            },
            provider=HookProvider.CODEX,
        )

        response = build_permission_response(DialogButton.ALWAYS_ALLOW, payload)

        assert (
            json.loads(
                runner_module._render_hook_response(
                    response,
                    provider=HookProvider.CODEX,
                    input_payload=payload,
                )
            )
            == {}
        )

    def test_claude_stop_response_includes_supported_top_level_fields(self) -> None:
        payload = build_hook_payload(
            {
                "hook_event_name": "Stop",
                "last_assistant_message": "Done.",
            }
        )

        response = HookResponse(
            continue_=False,
            stop_reason="Continue working.",
            system_message="One more step required.",
        )

        assert json.loads(
            runner_module._render_hook_response(
                response,
                provider=HookProvider.CLAUDE_CODE,
                input_payload=payload,
            )
        ) == {
            "continue": False,
            "stopReason": "Continue working.",
            "suppressOutput": True,
            "systemMessage": "One more step required.",
        }

    def test_codex_stop_response_omits_suppress_output(self) -> None:
        payload = build_hook_payload(
            {
                "hook_event_name": "Stop",
                "cwd": "/tmp/project",
                "last_assistant_message": "Done.",
                "model": "gpt-5.4",
                "permission_mode": "default",
                "session_id": "session-1",
                "stop_hook_active": False,
                "transcript_path": None,
                "turn_id": "turn-1",
            },
            provider=HookProvider.CODEX,
        )

        response = HookResponse(
            decision=HookControlDecision.BLOCK,
            reason="Run one more pass.",
            system_message="Continuing.",
        )

        assert json.loads(
            runner_module._render_hook_response(
                response,
                provider=HookProvider.CODEX,
                input_payload=payload,
            )
        ) == {
            "decision": "block",
            "reason": "Run one more pass.",
            "systemMessage": "Continuing.",
        }


class TestAgentHookFallback:
    def test_dispatch_uses_configured_fallback_handler(self) -> None:
        class CustomFallbackHandler:
            def __init__(self) -> None:
                self.seen_events: list[HookEventName] = []

            def handle(
                self,
                payload: HookPayload,
                transport: DisplayTransport,
                *,
                current_error: str | None = None,
            ) -> HookProcessingResult:
                self.seen_events.append(payload.event_name)
                assert current_error is None
                assert isinstance(transport, FakeTransport)
                return HookProcessingResult(
                    display=None,
                    transport_result=None,
                    response=HookResponse(suppress_output=False),
                )

        fallback_handler = CustomFallbackHandler()
        hook = AgentHook(fallback_handler=fallback_handler)
        input_data = read_hook_input(StringIO('{"hook_event_name":"PermissionRequest"}'))

        result = hook.dispatch(input_data, FakeTransport())

        assert fallback_handler.seen_events == [HookEventName.PERMISSION_REQUEST]
        assert result.response.as_payload() == {"suppressOutput": False}

    def test_fallback_handler_none_disables_fallback(self) -> None:
        hook = AgentHook(fallback_handler=None)
        input_data = read_hook_input(StringIO('{"hook_event_name":"PermissionRequest"}'))
        transport = FakeTransport()

        result = hook.dispatch(input_data, transport)

        assert transport.dialog_calls == 0
        assert result.response.as_payload() == {"suppressOutput": True}

    def test_legacy_fallback_flag_false_disables_fallback(self) -> None:
        hook = AgentHook(fallback_to_default_processor=False)
        input_data = read_hook_input(StringIO('{"hook_event_name":"PermissionRequest"}'))
        transport = FakeTransport()

        result = hook.dispatch(input_data, transport)

        assert transport.dialog_calls == 0
        assert result.response.as_payload() == {"suppressOutput": True}

    def test_default_hook_handler_handles_permission_request(self) -> None:
        hook = AgentHook(fallback_handler=DefaultHookHandler())
        input_data = read_hook_input(StringIO('{"hook_event_name":"PermissionRequest"}'))
        transport = FakeTransport()

        result = hook.dispatch(input_data, transport)

        assert transport.dialog_calls == 1
        assert result.response.as_payload() == {
            "suppressOutput": True,
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "allow"},
            },
        }

    def test_rejects_mixed_fallback_configuration_styles(self) -> None:
        with pytest.raises(
            ValueError,
            match="Use fallback_handler or fallback_to_default_processor",
        ):
            AgentHook(
                fallback_handler=DefaultHookHandler(),
                fallback_to_default_processor=False,
            )

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

        result = AgentHook().dispatch(input_data, transport)

        assert result.error == "notification failed"
        assert result.response.as_payload() == {"suppressOutput": True}

    def test_codex_permission_request_skips_dialog_when_execpolicy_allows(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        input_data = read_hook_input(
            StringIO(
                """
                {
                  "hook_event_name": "PreToolUse",
                  "cwd": "/tmp/project",
                  "model": "gpt-5.4",
                  "permission_mode": "default",
                  "session_id": "session-1",
                  "tool_input": {"command": "git status"},
                  "tool_name": "Bash",
                  "tool_use_id": "tool-1",
                  "transcript_path": null,
                  "turn_id": "turn-1"
                }
                """
            ),
            provider=HookProvider.CODEX,
        )
        transport = FakeTransport()
        monkeypatch.setattr(
            "agent_hooks.providers.codex.middleware.should_auto_allow_codex_permission_request",
            lambda _payload: True,
        )

        result = app.dispatch(input_data, transport)

        assert transport.dialog_calls == 0
        assert result.response.as_payload() == {"suppressOutput": True}


class TestCodexExecPolicy:
    def test_run_codex_execpolicy_check_returns_allow_and_uses_expected_command(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        captured_command: list[str] | None = None
        captured_cwd: str | None = None
        rules_path = tmp_path / "default.rules"
        rules_path.write_text('prefix_rule("git", "status") => allow', encoding="utf-8")

        def fake_run(
            command: list[str],
            *,
            capture_output: bool,
            text: bool,
            check: bool,
            cwd: str | None,
        ) -> object:
            nonlocal captured_command, captured_cwd
            captured_command = command
            captured_cwd = cwd
            assert capture_output is True
            assert text is True
            assert check is False

            class FakeCompletedProcess:
                returncode = 0
                stdout = (
                    '{"matchedRules":[{"prefixRuleMatch":{"decision":"allow"}}],"decision":"allow"}'
                )

            return FakeCompletedProcess()

        monkeypatch.setattr("agent_hooks.providers.codex.middleware.subprocess.run", fake_run)

        decision = run_codex_execpolicy_check(
            ["prek", "run", "ruff"],
            cwd="/tmp/project",
            env={CODEX_EXECPOLICY_RULES_ENV_VAR: str(rules_path)},
        )

        assert decision == "allow"
        assert captured_command == [
            "codex",
            "execpolicy",
            "check",
            "-c",
            'model="5.4-mini"',
            "--rules",
            str(rules_path),
            "--",
            "prek",
            "run",
            "ruff",
        ]
        assert captured_cwd == "/tmp/project"

    def test_run_codex_execpolicy_check_returns_empty_on_invalid_json(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        rules_path = tmp_path / "default.rules"
        rules_path.write_text('prefix_rule("git", "status") => allow', encoding="utf-8")

        def fake_run(
            _command: list[str],
            *,
            capture_output: bool,
            text: bool,
            check: bool,
            cwd: str | None,
        ) -> object:
            assert capture_output is True
            assert text is True
            assert check is False
            assert cwd is None

            class FakeCompletedProcess:
                returncode = 0
                stdout = "not-json"

            return FakeCompletedProcess()

        monkeypatch.setattr("agent_hooks.providers.codex.middleware.subprocess.run", fake_run)

        decision = run_codex_execpolicy_check(
            ["git", "status"],
            env={CODEX_EXECPOLICY_RULES_ENV_VAR: str(rules_path)},
        )

        assert decision == ""


class TestAgentHook:
    @pytest.mark.parametrize(
        ("event_model", "expected_fields", "unexpected_fields"),
        [
            pytest.param(
                NotificationEvent,
                {
                    "raw",
                    "provider",
                    "event_name",
                    "raw_event_name",
                    "model",
                    "session_id",
                    "cwd",
                    "transcript_path",
                    "raw_notification_type",
                    "title",
                    "message",
                },
                {"permission_mode", "tool_name", "tool_use_id", "tool_input", "error_details"},
                id="notification",
            ),
            pytest.param(
                PermissionRequestEvent,
                {
                    "raw",
                    "provider",
                    "event_name",
                    "raw_event_name",
                    "model",
                    "session_id",
                    "cwd",
                    "transcript_path",
                    "permission_mode",
                    "prompt",
                    "source",
                    "tool_name",
                    "tool_use_id",
                    "tool_input",
                },
                {"title", "message", "raw_notification_type", "error_details"},
                id="permission",
            ),
            pytest.param(
                SessionStartEvent,
                {
                    "raw",
                    "provider",
                    "event_name",
                    "raw_event_name",
                    "model",
                    "session_id",
                    "cwd",
                    "transcript_path",
                    "permission_mode",
                },
                {"title", "message", "tool_name", "tool_input", "error_details"},
                id="session-start",
            ),
            pytest.param(
                UserPromptSubmitEvent,
                {
                    "raw",
                    "provider",
                    "event_name",
                    "raw_event_name",
                    "model",
                    "session_id",
                    "cwd",
                    "transcript_path",
                    "prompt",
                    "source",
                    "last_assistant_message",
                },
                {"title", "message", "tool_name", "tool_input", "error_details"},
                id="user-prompt-submit",
            ),
            pytest.param(
                PostToolUseEvent,
                {
                    "raw",
                    "provider",
                    "event_name",
                    "raw_event_name",
                    "model",
                    "session_id",
                    "cwd",
                    "transcript_path",
                    "tool_name",
                    "tool_use_id",
                    "tool_input",
                    "last_assistant_message",
                },
                {"title", "message", "permission_mode", "error_details"},
                id="post-tool-use",
            ),
            pytest.param(
                StopEvent,
                {
                    "raw",
                    "provider",
                    "event_name",
                    "raw_event_name",
                    "model",
                    "session_id",
                    "cwd",
                    "transcript_path",
                    "last_assistant_message",
                },
                {"title", "message", "tool_name", "tool_input", "error_details"},
                id="stop",
            ),
            pytest.param(
                StopFailureEvent,
                {
                    "raw",
                    "provider",
                    "event_name",
                    "raw_event_name",
                    "model",
                    "session_id",
                    "cwd",
                    "transcript_path",
                    "last_assistant_message",
                    "error_details",
                    "error",
                },
                {"title", "message", "tool_name", "tool_input", "permission_mode"},
                id="stop-failure",
            ),
        ],
    )
    def test_route_event_models_expose_dedicated_fields(
        self,
        event_model: type[object],
        expected_fields: set[str],
        unexpected_fields: set[str],
    ) -> None:
        field_names = {field.name for field in fields(event_model)}

        assert expected_fields <= field_names
        assert unexpected_fields.isdisjoint(field_names)

    def test_router_middleware_wraps_dispatch(self) -> None:
        hook = AgentHook(fallback_handler=None)
        seen_tools: list[str] = []

        @hook.middleware()
        def capture_tool_name(context, call_next):
            seen_tools.append(context.payload.tool_name)
            return call_next(context)

        @hook.permission()
        def permission_callback() -> HookResponse:
            return HookResponse(suppress_output=False)

        input_data = read_hook_input(
            StringIO(
                """
                {
                  "hook_event_name": "PermissionRequest",
                  "tool_name": "Bash",
                  "tool_input": {"command": "git status"}
                }
                """
            )
        )

        result = hook.dispatch(input_data, FakeTransport())

        assert seen_tools == ["Bash"]
        assert result.response.as_payload() == {"suppressOutput": False}

    def test_permission_decorator_accepts_custom_response_model(self) -> None:
        hook = AgentHook()

        class CustomResponse:
            suppress_output = False
            hook_specific_output = None

            def as_payload(self) -> dict[str, bool]:
                return {"suppressOutput": self.suppress_output}

        @hook.permission()
        def permission_callback():
            return CustomResponse()

        input_data = read_hook_input(StringIO('{"hook_event_name":"PermissionRequest"}'))

        result = hook.dispatch(input_data, FakeTransport())

        assert result.response.as_payload() == {"suppressOutput": False}

    def test_permission_decorator_supports_transport_injection(self) -> None:
        hook = AgentHook(fallback_handler=None)

        @hook.permission()
        def permission_callback(
            hook_event: PermissionRequestEvent,
            transport: DisplayTransport,
        ) -> HookProcessingResult:
            return process_permission_request(hook_event, transport)

        input_data = read_hook_input(StringIO('{"hook_event_name":"PermissionRequest"}'))
        transport = FakeTransport()

        result = hook.dispatch(input_data, transport)

        assert transport.dialog_calls == 1
        assert result.response.as_payload() == {
            "suppressOutput": True,
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "allow"},
            },
        }

    def test_permission_decorator_injects_annotated_parameters_by_type(self) -> None:
        hook = AgentHook()

        @hook.permission()
        def permission_callback(
            hook_event: PermissionRequestEvent,
            request: CallbackRequest,
            label: str = "default-label",
        ) -> AppleScriptDialogResponse:
            assert hook_event.tool_name == "Bash"
            assert request.payload.tool_name == hook_event.tool_name
            assert label == "default-label"
            return build_permission_response(DialogButton.ALWAYS_ALLOW, hook_event)

        input_data = read_hook_input(
            StringIO(
                """
                {
                  "hook_event_name": "PermissionRequest",
                  "tool_name": "Bash",
                  "tool_input": {"command": "git status"},
                  "permission_suggestions": [
                    {
                      "id": "suggestion-1",
                      "rules": [{"toolName": "Bash", "ruleContent": "git *"}]
                    }
                  ]
                }
                """
            )
        )
        transport = FakeTransport()

        result = hook.dispatch(input_data, transport)

        assert transport.dialog_calls == 0
        assert result.response.as_payload() == {
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

    def test_permission_decorator_supports_depends_injection(self) -> None:
        hook = AgentHook()

        def build_command_context(
            request: CallbackRequest,
            hook_event: PermissionRequestEvent,
        ) -> str:
            assert request.payload.tool_name == hook_event.tool_name
            return f"{hook_event.tool_name}:{hook_event.tool_input.command}"

        @hook.permission()
        def permission_callback(
            command_context: str = Depends(build_command_context),
        ) -> HookResponse:
            assert command_context == "Bash:git status"
            return HookResponse(suppress_output=False)

        input_data = read_hook_input(
            StringIO(
                """
                {
                  "hook_event_name": "PermissionRequest",
                  "tool_name": "Bash",
                  "tool_input": {"command": "git status"}
                }
                """
            )
        )

        result = hook.dispatch(input_data, FakeTransport())

        assert result.response.as_payload() == {"suppressOutput": False}

    def test_permission_decorator_supports_class_dependency_injection(self) -> None:
        hook = AgentHook()

        class CommandContext:
            def __init__(
                self,
                request: CallbackRequest,
                hook_event: PermissionRequestEvent,
            ) -> None:
                assert request.payload.tool_name == hook_event.tool_name
                self.value = f"{hook_event.tool_name}:{hook_event.tool_input.command}"

        command_context_dependency = Depends(CommandContext)

        @hook.permission()
        def permission_callback(
            context: object = command_context_dependency,
        ) -> HookResponse:
            assert isinstance(context, CommandContext)
            assert context.value == "Bash:git status"
            return HookResponse(suppress_output=False)

        input_data = read_hook_input(
            StringIO(
                """
                {
                  "hook_event_name": "PermissionRequest",
                  "tool_name": "Bash",
                  "tool_input": {"command": "git status"}
                }
                """
            )
        )

        result = hook.dispatch(input_data, FakeTransport())

        assert result.response.as_payload() == {"suppressOutput": False}

    def test_permission_decorator_supports_class_dependency_without_init(self) -> None:
        hook = AgentHook()

        class Marker:
            pass

        marker_dependency = Depends(Marker)

        @hook.permission()
        def permission_callback(
            marker: object = marker_dependency,
        ) -> HookResponse:
            assert isinstance(marker, Marker)
            return HookResponse(suppress_output=False)

        input_data = read_hook_input(
            StringIO('{"hook_event_name":"PermissionRequest","tool_name":"Bash"}')
        )

        result = hook.dispatch(input_data, FakeTransport())

        assert result.response.as_payload() == {"suppressOutput": False}

    def test_permission_decorator_supports_unhashable_callable_dependency(self) -> None:
        hook = AgentHook()

        class Builder:
            __hash__ = None  # unhashable, like a non-frozen dataclass with __call__

            def __call__(self) -> str:
                return "ctx"

        builder_dependency = Depends(Builder())

        @hook.permission()
        def permission_callback(
            context: str = builder_dependency,
        ) -> HookResponse:
            assert context == "ctx"
            return HookResponse(suppress_output=False)

        input_data = read_hook_input(
            StringIO('{"hook_event_name":"PermissionRequest","tool_name":"Bash"}')
        )

        result = hook.dispatch(input_data, FakeTransport())

        assert result.response.as_payload() == {"suppressOutput": False}

    def test_handler_with_unresolvable_annotation_registers(self) -> None:
        hook = AgentHook()

        @hook.permission()
        def permission_callback(
            value: UndefinedForwardRef = "fallback",  # noqa: F821
        ) -> HookResponse:
            assert value == "fallback"
            return HookResponse(suppress_output=False)

        input_data = read_hook_input(
            StringIO('{"hook_event_name":"PermissionRequest","tool_name":"Bash"}')
        )

        result = hook.dispatch(input_data, FakeTransport())

        assert result.response.as_payload() == {"suppressOutput": False}

    def test_yield_dependency_receives_handler_exception(self) -> None:
        hook = AgentHook()
        events: list[str] = []

        def open_connection() -> object:
            try:
                yield "db-session"
            except RuntimeError:
                events.append("rolled-back")
                raise
            else:
                events.append("committed")

        @hook.permission()
        def permission_callback(
            connection: str = Depends(open_connection),
        ) -> HookResponse:
            raise RuntimeError("boom")

        input_data = read_hook_input(StringIO('{"hook_event_name":"PermissionRequest"}'))

        with pytest.raises(RuntimeError, match="boom"):
            hook.dispatch(input_data, FakeTransport())

        # The handler exception must be thrown into the generator so its except runs.
        assert events == ["rolled-back"]

    def test_yield_dependency_closed_when_it_yields_again_after_error(self) -> None:
        hook = AgentHook()
        events: list[str] = []

        def open_connection() -> object:
            try:
                yield "db-session"
            except RuntimeError:
                events.append("caught")
                yield "second"
            finally:
                events.append("closed")

        @hook.permission()
        def permission_callback(
            connection: str = Depends(open_connection),
        ) -> HookResponse:
            raise RuntimeError("boom")

        input_data = read_hook_input(StringIO('{"hook_event_name":"PermissionRequest"}'))

        with pytest.raises(ValueError, match="must yield exactly one value"):
            hook.dispatch(input_data, FakeTransport())

        # The misbehaving generator must be closed (running its finally) before the
        # single-yield error is raised, rather than leaking until garbage collection.
        assert events == ["caught", "closed"]

    def test_permission_decorator_supports_yield_dependency_cleanup(self) -> None:
        hook = AgentHook()
        events: list[str] = []

        def open_connection() -> object:
            events.append("open")
            try:
                yield "db-session"
            finally:
                events.append("close")

        @hook.permission()
        def permission_callback(
            connection: str = Depends(open_connection),
        ) -> HookResponse:
            events.append(f"use:{connection}")
            return HookResponse(suppress_output=False)

        input_data = read_hook_input(StringIO('{"hook_event_name":"PermissionRequest"}'))

        result = hook.dispatch(input_data, FakeTransport())

        assert result.response.as_payload() == {"suppressOutput": False}
        assert events == ["open", "use:db-session", "close"]

    def test_permission_decorator_supports_contextmanager_dependency(self) -> None:
        hook = AgentHook()
        events: list[str] = []

        @contextmanager
        def open_connection() -> object:
            events.append("open")
            try:
                yield "db-session"
            finally:
                events.append("close")

        @hook.permission()
        def permission_callback(
            connection: str = Depends(open_connection),
        ) -> HookResponse:
            events.append(f"use:{connection}")
            return HookResponse(suppress_output=False)

        input_data = read_hook_input(StringIO('{"hook_event_name":"PermissionRequest"}'))

        result = hook.dispatch(input_data, FakeTransport())

        assert result.response.as_payload() == {"suppressOutput": False}
        assert events == ["open", "use:db-session", "close"]

    def test_yield_dependency_cleanup_runs_when_handler_raises(self) -> None:
        hook = AgentHook()
        events: list[str] = []

        def open_connection() -> object:
            events.append("open")
            try:
                yield "db-session"
            finally:
                events.append("close")

        @hook.permission()
        def permission_callback(
            connection: str = Depends(open_connection),
        ) -> HookResponse:
            events.append(f"use:{connection}")
            raise RuntimeError("boom")

        input_data = read_hook_input(StringIO('{"hook_event_name":"PermissionRequest"}'))

        with pytest.raises(RuntimeError, match="boom"):
            hook.dispatch(input_data, FakeTransport())

        assert events == ["open", "use:db-session", "close"]

    def test_notification_decorator_injects_notification_specific_schema(self) -> None:
        hook = AgentHook(fallback_handler=None)

        @hook.notification()
        def notification_callback(hook_event: NotificationEvent) -> HookResponse:
            assert hook_event.title == "Build complete"
            assert hook_event.message == "All checks passed."
            assert hook_event.raw_notification_type == "task_completed"
            assert not hasattr(hook_event, "tool_name")
            return HookResponse(suppress_output=False)

        input_data = read_hook_input(
            StringIO(
                """
                {
                  "hook_event_name": "Notification",
                  "notification_type": "task_completed",
                  "title": "Build complete",
                  "message": "All checks passed.",
                  "tool_name": "Bash",
                  "tool_input": {"command": "pytest"}
                }
                """
            )
        )

        result = hook.dispatch(input_data, FakeTransport())

        assert result.response.as_payload() == {"suppressOutput": False}

    def test_permission_decorator_supports_partial_signature_injection(self) -> None:
        hook = AgentHook()

        @hook.permission()
        def permission_callback(hook_event: PermissionRequestEvent) -> HookResponse:
            assert hook_event.tool_input.command == "git status"
            return HookResponse(suppress_output=False)

        input_data = read_hook_input(
            StringIO(
                """
                {
                  "hook_event_name": "PermissionRequest",
                  "tool_name": "Bash",
                  "tool_input": {"command": "git status"}
                }
                """
            )
        )

        result = hook.dispatch(input_data, FakeTransport())

        assert result.response.as_payload() == {"suppressOutput": False}

    def test_permission_decorator_supports_zero_argument_handler(self) -> None:
        hook = AgentHook()

        @hook.permission()
        def permission_callback() -> HookResponse:
            return HookResponse(suppress_output=False)

        input_data = read_hook_input(StringIO('{"hook_event_name":"PermissionRequest"}'))

        result = hook.dispatch(input_data, FakeTransport())

        assert result.response.as_payload() == {"suppressOutput": False}

    def test_dispatch_falls_back_to_default_handler(self) -> None:
        hook = AgentHook()
        input_data = read_hook_input(
            StringIO(
                """
                {
                  "hook_event_name": "PermissionRequest",
                  "tool_name": "Bash",
                  "tool_input": {"command": "git status"}
                }
                """
            )
        )
        transport = FakeTransport()

        result = hook.dispatch(input_data, transport)

        assert transport.dialog_calls == 1
        assert result.response.as_payload() == {
            "suppressOutput": True,
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "allow"},
            },
        }

    def test_registering_required_unannotated_parameter_raises_value_error(self) -> None:
        hook = AgentHook()

        with pytest.raises(
            ValueError,
            match="CallbackRequest, DisplayTransport, or PermissionRequestEvent",
        ):

            @hook.permission()
            def permission_callback(request: CallbackRequest, label) -> AppleScriptDialogResponse:
                return build_permission_response(DialogButton.ALLOW_ONCE, request.payload)

    def test_registering_non_matching_event_annotation_raises_value_error(self) -> None:
        hook = AgentHook()

        with pytest.raises(
            ValueError,
            match="CallbackRequest, DisplayTransport, or PermissionRequestEvent",
        ):

            @hook.permission()
            def permission_callback(hook_event: NotificationEvent) -> HookResponse:
                return HookResponse()

    def test_registering_duplicate_handler_raises_value_error(self) -> None:
        hook = AgentHook()

        @hook.permission()
        def permission_callback(
            request: CallbackRequest,
            hook_event: PermissionRequestEvent,
        ) -> AppleScriptDialogResponse:
            assert request.payload.event_name == hook_event.event_name
            return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)

        with pytest.raises(ValueError, match="PermissionRequest"):

            @hook.permission()
            def duplicate_permission_callback(
                request: CallbackRequest,
                hook_event: PermissionRequestEvent,
            ) -> AppleScriptDialogResponse:
                assert request.payload.event_name == hook_event.event_name
                return build_permission_response(DialogButton.DENY, hook_event)

    def test_registering_nested_depends_raises_value_error(self) -> None:
        hook = AgentHook()

        def build_tool_name(request: CallbackRequest) -> str:
            return request.payload.tool_name

        def build_context(tool_name: str = Depends(build_tool_name)) -> str:
            return tool_name

        with pytest.raises(ValueError, match="Only one dependency level is supported"):

            @hook.permission()
            def permission_callback(
                context: str = Depends(build_context),
            ) -> HookResponse:
                return HookResponse(suppress_output=False)

    def test_registering_dependency_with_unsupported_parameter_raises_value_error(self) -> None:
        hook = AgentHook()

        def build_context(label) -> str:
            return label

        with pytest.raises(
            ValueError,
            match="Dependency 'build_context' has unsupported required parameter 'label'",
        ):

            @hook.permission()
            def permission_callback(
                context: str = Depends(build_context),
            ) -> HookResponse:
                return HookResponse(suppress_output=False)

    def test_dispatch_raises_for_yield_dependency_without_value(self) -> None:
        hook = AgentHook()

        def open_connection() -> object:
            if False:
                yield "db-session"

        @hook.permission()
        def permission_callback(
            connection: str = Depends(open_connection),
        ) -> HookResponse:
            return HookResponse(suppress_output=False)

        input_data = read_hook_input(StringIO('{"hook_event_name":"PermissionRequest"}'))

        with pytest.raises(ValueError, match="must yield exactly one value"):
            hook.dispatch(input_data, FakeTransport())

    def test_dispatch_raises_for_yield_dependency_with_multiple_values(self) -> None:
        hook = AgentHook()

        def open_connection() -> object:
            yield "db-session"
            yield "db-session-2"

        @hook.permission()
        def permission_callback(
            connection: str = Depends(open_connection),
        ) -> HookResponse:
            return HookResponse(suppress_output=False)

        input_data = read_hook_input(StringIO('{"hook_event_name":"PermissionRequest"}'))

        with pytest.raises(ValueError, match="must yield exactly one value"):
            hook.dispatch(input_data, FakeTransport())


class TestRuntimeConfig:
    def test_load_runtime_config_caches_process_environment(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        load_runtime_config.cache_clear()
        monkeypatch.setenv("AGENT_HOOK_PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("AGENT_HOOK_DIALOG_FONT_SIZE", "18")

        config = load_runtime_config()
        monkeypatch.setenv("AGENT_HOOK_DIALOG_FONT_SIZE", "21")

        assert load_runtime_config() is config
        assert config.dialog_font_size == 18
        load_runtime_config.cache_clear()

    def test_load_runtime_config_reads_environment_overrides(self, tmp_path: Path) -> None:
        env = {
            "AGENT_HOOK_PROJECT_ROOT": str(tmp_path),
            "AGENT_HOOK_LOG_DIR": "var/logs",
            "AGENT_HOOK_PROVIDER": "codex",
            "AGENT_HOOK_DISABLE_OSASCRIPT": "true",
            "AGENT_HOOK_APP_LOG_PATH": "runtime/app.log",
            "AGENT_HOOK_APP_LOG_FORMAT": "%(levelname)s %(message)s",
            "AGENT_HOOK_APP_LOG_LEVEL": "debug",
            "AGENT_HOOK_LOG_MAX_BYTES": "2048",
            "AGENT_HOOK_LOG_BACKUP_COUNT": "6",
            "AGENT_HOOK_RESPONSE_AUDIT_LOG_PATH": "runtime/response.log",
            "AGENT_HOOK_DIALOG_FONT_SIZE": "18",
            "AGENT_HOOK_COMMAND_PREVIEW_MAX_TOTAL_CHARS": "120",
            "AGENT_HOOK_COMMAND_PREVIEW_MAX_TOTAL_LINES": "4",
            "AGENT_HOOK_COMMAND_PREVIEW_MAX_LINE_CHARS": "40",
            "AGENT_HOOK_NOTIFICATION_TIMEOUT": "5.5",
        }

        config = load_runtime_config(env)

        assert config.project_root == tmp_path
        assert config.log_directory == tmp_path / "var" / "logs"
        assert config.provider == HookProvider.CODEX
        assert config.skip_osascript is True
        assert config.application_logging.file.path == tmp_path / "runtime" / "app.log"
        assert config.application_logging.level == logging.DEBUG
        assert config.application_logging.level_name == "DEBUG"
        assert config.application_logging.format_string == "%(levelname)s %(message)s"
        assert config.audit_logging.input_file.max_bytes == 2048
        assert config.audit_logging.response_file.backup_count == 6
        assert config.audit_logging.response_file.path == tmp_path / "runtime" / "response.log"
        assert config.dialog_font_size == 18
        assert config.command_preview_max_total_chars == 120
        assert config.command_preview_max_total_lines == 4
        assert config.command_preview_max_line_chars == 40
        assert config.notification_timeout_seconds == 5.5

    def test_load_runtime_config_leaves_provider_unset_by_default(self) -> None:
        config = load_runtime_config({})

        assert config.provider is None
        assert config.dialog_font_size == DEFAULT_DIALOG_FONT_SIZE
        assert config.command_preview_max_total_chars == DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_CHARS
        assert config.command_preview_max_total_lines == DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_LINES
        assert config.command_preview_max_line_chars == DEFAULT_COMMAND_PREVIEW_MAX_LINE_CHARS
        assert config.notification_timeout_seconds == DEFAULT_NOTIFICATION_TIMEOUT_SECONDS

    def test_load_runtime_config_allows_disabling_notification_timeout(self) -> None:
        config = load_runtime_config({"AGENT_HOOK_NOTIFICATION_TIMEOUT": "0"})

        assert config.notification_timeout_seconds == 0.0
        assert config.warnings == ()

    def test_load_runtime_config_ignores_invalid_notification_timeout(self) -> None:
        config = load_runtime_config({"AGENT_HOOK_NOTIFICATION_TIMEOUT": "-2"})

        assert config.notification_timeout_seconds == DEFAULT_NOTIFICATION_TIMEOUT_SECONDS
        assert config.warnings == (
            "Negative number value for AGENT_HOOK_NOTIFICATION_TIMEOUT: '-2'. Using fallback.",
        )

    def test_load_runtime_config_ignores_invalid_dialog_font_size(self) -> None:
        config = load_runtime_config({"AGENT_HOOK_DIALOG_FONT_SIZE": "0"})

        assert config.dialog_font_size == DEFAULT_DIALOG_FONT_SIZE
        assert config.warnings == (
            "Non-positive integer value for AGENT_HOOK_DIALOG_FONT_SIZE: '0'. Using fallback.",
        )

    def test_load_runtime_config_ignores_invalid_command_preview_limits(self) -> None:
        config = load_runtime_config(
            {
                "AGENT_HOOK_COMMAND_PREVIEW_MAX_TOTAL_CHARS": "0",
                "AGENT_HOOK_COMMAND_PREVIEW_MAX_TOTAL_LINES": "nope",
                "AGENT_HOOK_COMMAND_PREVIEW_MAX_LINE_CHARS": "-1",
            }
        )

        assert config.command_preview_max_total_chars == DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_CHARS
        assert config.command_preview_max_total_lines == DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_LINES
        assert config.command_preview_max_line_chars == DEFAULT_COMMAND_PREVIEW_MAX_LINE_CHARS
        assert config.warnings == (
            "Non-positive integer value for AGENT_HOOK_COMMAND_PREVIEW_MAX_TOTAL_CHARS: '0'. "
            "Using fallback.",
            "Invalid integer value for AGENT_HOOK_COMMAND_PREVIEW_MAX_TOTAL_LINES: 'nope'. "
            "Using fallback.",
            "Non-positive integer value for AGENT_HOOK_COMMAND_PREVIEW_MAX_LINE_CHARS: '-1'. "
            "Using fallback.",
        )


class TestAgentHookFileLoader:
    def test_module_name_from_path_uses_app_dir(self, tmp_path: Path) -> None:
        loader = runner_module.AgentHookFileLoader(app_dir=tmp_path)
        module_path = tmp_path / "package" / "main.py"
        module_path.parent.mkdir()
        module_path.write_text("", encoding="utf-8")

        module_name = loader._module_name_from_path(module_path)

        assert module_name == "package.main"

    def test_discover_agent_hook_name_from_python_file(self, tmp_path: Path) -> None:
        loader = runner_module.AgentHookFileLoader(app_dir=tmp_path)
        module_path = tmp_path / "file_discovery_hooks.py"
        write_app_module(module_path)

        discovered_name = loader._discover_agent_hook_name(module_path)

        assert discovered_name == "app"

    def test_discover_agent_hook_name_raises_when_missing_instance(self, tmp_path: Path) -> None:
        loader = runner_module.AgentHookFileLoader(app_dir=tmp_path)
        module_path = tmp_path / "missing_hooks.py"
        module_path.write_text(
            "from __future__ import annotations\n\nvalue = 1\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="No top-level AgentHook"):
            loader._discover_agent_hook_name(module_path)

    def test_load_supports_python_file(self, tmp_path: Path) -> None:
        loader = runner_module.AgentHookFileLoader(app_dir=tmp_path)
        module_path = tmp_path / "file_run_hooks.py"
        write_app_module(module_path)

        target = loader.load("file_run_hooks.py")

        assert isinstance(target, AgentHook)

    def test_load_isolates_same_filename_across_app_dirs(self, tmp_path: Path) -> None:
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        write_app_module(dir_a / "hooks.py")
        write_app_module(dir_b / "hooks.py")

        app_a = runner_module.AgentHookFileLoader(app_dir=dir_a).load("hooks.py")
        app_b = runner_module.AgentHookFileLoader(app_dir=dir_b).load("hooks.py")

        # Same file name in different directories must load distinct apps, not a stale
        # sys.modules entry from the first load.
        assert isinstance(app_a, AgentHook)
        assert isinstance(app_b, AgentHook)
        assert app_a is not app_b


class TestRunCallback:
    def test_builtin_app_registers_codex_routes(self) -> None:
        assert HookEventName.PERMISSION_REQUEST in app._routes
        assert HookEventName.SESSION_START in app._routes
        assert HookEventName.USER_PROMPT_SUBMIT in app._routes
        assert HookEventName.POST_TOOL_USE in app._routes
        assert HookEventName.STOP in app._routes

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
        runtime_config = build_runtime_config(tmp_path)

        exit_code = run_callback(
            app,
            stdin=stdin,
            stdout=stdout,
            runtime_config=runtime_config,
            transport=FakeTransport(),
        )

        assert exit_code == 0
        assert stdout.getvalue() == (
            '{"suppressOutput":true,"hookSpecificOutput":{"hookEventName":"PermissionRequest",'
            '"decision":{"behavior":"allow"}}}\n'
        )
        input_audit_record = json.loads(runtime_config.raw_log_path.read_text(encoding="utf-8"))
        assert input_audit_record["provider"] == "claude-code"
        assert input_audit_record["hook_event_name"] == "PermissionRequest"
        assert input_audit_record["raw_input"].strip().startswith("{")

        response_audit_record = json.loads(
            runtime_config.response_log_path.read_text(encoding="utf-8")
        )
        assert response_audit_record["provider"] == "claude-code"
        assert response_audit_record["hook_event_name"] == "PermissionRequest"
        assert response_audit_record["hook_response"] == stdout.getvalue()

        app_log = runtime_config.log_path.read_text(encoding="utf-8")
        assert app_log.startswith("INFO ")
        assert '"provider": "claude-code"' in app_log
        assert '"hook_event_name": "PermissionRequest"' in app_log
        expected_response_bytes = len(stdout.getvalue().encode("utf-8"))
        assert f'"response_bytes": {expected_response_bytes}' in app_log

    def test_run_callback_passes_dialog_font_size_to_default_transport(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured_init: dict[str, object] = {}

        class FakeAppleScriptTransport:
            def __init__(
                self,
                *,
                skip_osascript: bool,
                dialog_font_size: int = DEFAULT_DIALOG_FONT_SIZE,
                notification_timeout: float = DEFAULT_NOTIFICATION_TIMEOUT_SECONDS,
            ) -> None:
                captured_init["skip_osascript"] = skip_osascript
                captured_init["dialog_font_size"] = dialog_font_size
                captured_init["notification_timeout"] = notification_timeout

            def send_notification(self, notification: object) -> AppleScriptResult:
                return AppleScriptResult(
                    status=TransportStatus.SUCCEEDED,
                    invocation=AppleScriptInvocation.NOTIFICATION,
                )

            def show_dialog(self, dialog: object) -> DialogResult:
                return DialogResult(
                    button=DialogButton.ALLOW_ONCE,
                    transport=AppleScriptResult(
                        status=TransportStatus.SUCCEEDED,
                        invocation=AppleScriptInvocation.DIALOG,
                    ),
                )

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
        runtime_config = build_runtime_config(
            tmp_path,
            dialog_font_size=21,
            notification_timeout_seconds=7.5,
        )
        monkeypatch.setattr(runner_module, "AppleScriptTransport", FakeAppleScriptTransport)

        exit_code = run_callback(
            app,
            stdin=stdin,
            stdout=stdout,
            runtime_config=runtime_config,
        )

        assert exit_code == 0
        assert captured_init == {
            "skip_osascript": True,
            "dialog_font_size": 21,
            "notification_timeout": 7.5,
        }

    def test_run_callback_applies_configured_command_preview_limits(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        stdin = StringIO(
            """
            {
              "hook_event_name": "PreToolUse",
              "cwd": "/tmp/project",
              "model": "gpt-5.4",
              "permission_mode": "default",
              "session_id": "session-1",
              "tool_input": {"command": "1234567890\\nsecond\\nthird\\nfourth"},
              "tool_name": "Bash",
              "tool_use_id": "tool-1",
              "transcript_path": null,
              "turn_id": "turn-1"
            }
            """
        )
        stdout = StringIO()
        transport = FakeTransport()
        monkeypatch.setenv("AGENT_HOOK_PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("AGENT_HOOK_PROVIDER", "codex")
        monkeypatch.setenv("AGENT_HOOK_COMMAND_PREVIEW_MAX_TOTAL_CHARS", "20")
        monkeypatch.setenv("AGENT_HOOK_COMMAND_PREVIEW_MAX_TOTAL_LINES", "2")
        load_runtime_config.cache_clear()

        exit_code = run_callback(
            app,
            stdin=stdin,
            stdout=stdout,
            transport=transport,
        )
        load_runtime_config.cache_clear()

        assert exit_code == 0
        assert len(transport.dialogs) == 1
        dialog = transport.dialogs[0]
        assert isinstance(dialog, DialogSpec)
        assert dialog.message == ("Tool: Bash\nCommand:\n1234567890\nsecond\n… +2 lines")

    def test_run_callback_applies_command_preview_limits_from_passed_runtime_config(
        self,
        tmp_path: Path,
    ) -> None:
        stdin = StringIO(
            """
            {
              "hook_event_name": "PreToolUse",
              "cwd": "/tmp/project",
              "model": "gpt-5.4",
              "permission_mode": "default",
              "session_id": "session-1",
              "tool_input": {"command": "1234567890\\nsecond\\nthird\\nfourth"},
              "tool_name": "Bash",
              "tool_use_id": "tool-1",
              "transcript_path": null,
              "turn_id": "turn-1"
            }
            """
        )
        stdout = StringIO()
        transport = FakeTransport()
        runtime_config = build_runtime_config(
            tmp_path,
            provider=HookProvider.CODEX,
            command_preview_max_total_chars=20,
            command_preview_max_total_lines=2,
        )

        exit_code = run_callback(
            app,
            stdin=stdin,
            stdout=stdout,
            transport=transport,
            runtime_config=runtime_config,
        )

        # Limits supplied programmatically (not via AGENT_HOOK_* env vars) must be honored.
        assert exit_code == 0
        assert len(transport.dialogs) == 1
        dialog = transport.dialogs[0]
        assert isinstance(dialog, DialogSpec)
        assert dialog.message == ("Tool: Bash\nCommand:\n1234567890\nsecond\n… +2 lines")

    def test_run_callback_limits_command_preview_line_width(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        stdin = StringIO(
            """
            {
              "hook_event_name": "PreToolUse",
              "cwd": "/tmp/project",
              "model": "gpt-5.4",
              "permission_mode": "default",
              "session_id": "session-1",
              "tool_input": {"command": "1234567890\\nabcdefghi\\nok"},
              "tool_name": "Bash",
              "tool_use_id": "tool-1",
              "transcript_path": null,
              "turn_id": "turn-1"
            }
            """
        )
        stdout = StringIO()
        transport = FakeTransport()
        monkeypatch.setenv("AGENT_HOOK_PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("AGENT_HOOK_PROVIDER", "codex")
        monkeypatch.setenv("AGENT_HOOK_COMMAND_PREVIEW_MAX_LINE_CHARS", "6")
        load_runtime_config.cache_clear()

        exit_code = run_callback(
            app,
            stdin=stdin,
            stdout=stdout,
            transport=transport,
        )
        load_runtime_config.cache_clear()

        assert exit_code == 0
        assert len(transport.dialogs) == 1
        dialog = transport.dialogs[0]
        assert isinstance(dialog, DialogSpec)
        assert dialog.message == ("Tool: Bash\nCommand:\n12345…\nabcde…\nok")

    def test_run_callback_supports_codex_provider(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        stdin = StringIO(
            """
            {
              "hook_event_name": "PreToolUse",
              "cwd": "/tmp/project",
              "model": "gpt-5.4",
              "permission_mode": "default",
              "session_id": "session-1",
              "tool_input": {"command": "git status"},
              "tool_name": "Bash",
              "tool_use_id": "tool-1",
              "transcript_path": null,
              "turn_id": "turn-1"
            }
            """
        )
        stdout = StringIO()
        runtime_config = build_runtime_config(tmp_path, provider=HookProvider.CODEX)
        monkeypatch.setattr(
            "agent_hooks.providers.codex.middleware.should_auto_allow_codex_permission_request",
            lambda _payload: False,
        )

        exit_code = run_callback(
            app,
            stdin=stdin,
            stdout=stdout,
            runtime_config=runtime_config,
            transport=FakeTransport(),
        )

        assert exit_code == 0
        assert json.loads(stdout.getvalue()) == {}

    def test_run_callback_auto_detects_codex_provider_for_pre_tool_use(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        stdin = StringIO(
            """
            {
              "hook_event_name": "PreToolUse",
              "cwd": "/tmp/project",
              "model": "gpt-5.4",
              "permission_mode": "default",
              "session_id": "session-1",
              "tool_input": {"command": "git status"},
              "tool_name": "Bash",
              "tool_use_id": "tool-1",
              "transcript_path": null,
              "turn_id": "turn-1"
            }
            """
        )
        stdout = StringIO()
        monkeypatch.setattr(
            "agent_hooks.providers.codex.middleware.should_auto_allow_codex_permission_request",
            lambda _payload: False,
        )

        exit_code = run_callback(
            app,
            stdin=stdin,
            stdout=stdout,
            runtime_config=load_runtime_config({}),
            transport=FakeTransport(),
        )

        assert exit_code == 0
        assert json.loads(stdout.getvalue()) == {}

    def test_run_callback_supports_codex_stop_event(
        self,
        tmp_path: Path,
    ) -> None:
        stdin = StringIO(
            """
            {
              "hook_event_name": "Stop",
              "cwd": "/tmp/project",
              "last_assistant_message": "Done.",
              "model": "gpt-5.4",
              "permission_mode": "default",
              "session_id": "session-1",
              "stop_hook_active": false,
              "transcript_path": null,
              "turn_id": "turn-1"
            }
            """
        )
        stdout = StringIO()
        transport = FakeTransport()

        exit_code = run_callback(
            app,
            stdin=stdin,
            stdout=stdout,
            runtime_config=build_runtime_config(tmp_path, provider=HookProvider.CODEX),
            transport=transport,
        )

        assert exit_code == 0
        assert transport.notification_calls == 1
        assert json.loads(stdout.getvalue()) == {}

    def test_run_callback_codex_denial_renders_pre_tool_use_decision(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        stdin = StringIO(
            """
            {
              "hook_event_name": "PreToolUse",
              "cwd": "/tmp/project",
              "model": "gpt-5.4",
              "permission_mode": "default",
              "session_id": "session-1",
              "tool_input": {"command": "git status"},
              "tool_name": "Bash",
              "tool_use_id": "tool-1",
              "transcript_path": null,
              "turn_id": "turn-1"
            }
            """
        )
        stdout = StringIO()
        runtime_config = build_runtime_config(tmp_path)
        transport = FakeTransport(
            dialog_result=DialogResult(
                button=DialogButton.DENY,
                transport=AppleScriptResult(
                    status=TransportStatus.SUCCEEDED,
                    invocation=AppleScriptInvocation.DIALOG,
                    stdout="button returned:Deny",
                ),
            )
        )
        monkeypatch.setattr(
            "agent_hooks.providers.codex.middleware.should_auto_allow_codex_permission_request",
            lambda _payload: False,
        )

        exit_code = run_callback(
            app,
            stdin=stdin,
            stdout=stdout,
            runtime_config=runtime_config,
            transport=transport,
            provider=HookProvider.CODEX,
        )

        assert exit_code == 0
        assert json.loads(stdout.getvalue()) == {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Permission denied by local user.",
            },
        }

    def test_run_callback_accepts_callback_instance(
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
        runtime_config = build_runtime_config(tmp_path)

        exit_code = run_callback(
            app,
            stdin=stdin,
            stdout=stdout,
            runtime_config=runtime_config,
            transport=FakeTransport(),
        )

        assert exit_code == 0
        assert stdout.getvalue() == (
            '{"suppressOutput":true,"hookSpecificOutput":{"hookEventName":"PermissionRequest",'
            '"decision":{"behavior":"allow"}}}\n'
        )

    def test_run_callback_builtin_app_uses_provider_middleware(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        stdin = StringIO(
            """
            {
              "hook_event_name": "PreToolUse",
              "cwd": "/tmp/project",
              "model": "gpt-5.4",
              "permission_mode": "default",
              "session_id": "session-1",
              "tool_input": {"command": "git status"},
              "tool_name": "Bash",
              "tool_use_id": "tool-1",
              "transcript_path": null,
              "turn_id": "turn-1"
            }
            """
        )
        stdout = StringIO()
        transport = FakeTransport()
        monkeypatch.setattr(
            "agent_hooks.providers.codex.middleware.should_auto_allow_codex_permission_request",
            lambda _payload: True,
        )

        exit_code = run_callback(
            app,
            stdin=stdin,
            stdout=stdout,
            runtime_config=build_runtime_config(tmp_path, provider=HookProvider.CODEX),
            transport=transport,
        )

        assert exit_code == 0
        assert transport.dialog_calls == 0
        assert json.loads(stdout.getvalue()) == {}

    def test_agent_hook_run_callback_uses_registered_handler(
        self,
        tmp_path: Path,
    ) -> None:
        hook = AgentHook()

        @hook.permission()
        def permission_callback(
            request: CallbackRequest,
            hook_event: PermissionRequestEvent,
        ) -> AppleScriptDialogResponse:
            assert hook_event.tool_input.command == "git status"
            assert request.payload.tool_input.command == hook_event.tool_input.command
            return build_permission_response(DialogButton.DENY, hook_event)

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
        runtime_config = build_runtime_config(tmp_path)

        exit_code = hook.run_callback(
            stdin=stdin,
            stdout=stdout,
            runtime_config=runtime_config,
            transport=FakeTransport(),
        )

        assert exit_code == 0
        assert stdout.getvalue() == (
            '{"suppressOutput":true,"hookSpecificOutput":{"hookEventName":"PermissionRequest",'
            '"decision":{"behavior":"deny"}}}\n'
        )

    def test_agent_hook_provider_is_used_by_default(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        hook = AgentHook(provider=HookProvider.CODEX)
        stdin = StringIO(
            """
            {
              "hook_event_name": "PreToolUse",
              "cwd": "/tmp/project",
              "model": "gpt-5.4",
              "permission_mode": "default",
              "session_id": "session-1",
              "tool_input": {"command": "git status"},
              "tool_name": "Bash",
              "tool_use_id": "tool-1",
              "transcript_path": null,
              "turn_id": "turn-1"
            }
            """
        )
        stdout = StringIO()
        runtime_config = build_runtime_config(tmp_path)
        monkeypatch.setattr(
            "agent_hooks.providers.codex.middleware.should_auto_allow_codex_permission_request",
            lambda _payload: False,
        )

        exit_code = hook.run_callback(
            stdin=stdin,
            stdout=stdout,
            runtime_config=runtime_config,
            transport=FakeTransport(),
        )

        assert exit_code == 0
        assert json.loads(stdout.getvalue()) == {}


class TestCliMain:
    def test_main_run_loads_python_file_target(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        module_path = tmp_path / "cli_file_hooks.py"
        write_app_module(module_path)
        captured_target: object | None = None
        captured_provider: str | None = None

        def fake_run_callback(target: object, *, provider: str | None = None) -> int:
            nonlocal captured_target
            nonlocal captured_provider
            captured_target = target
            captured_provider = provider
            return 27

        monkeypatch.setattr("agent_hooks.cli_app.cli.run_callback", fake_run_callback)

        exit_code = cli_main(
            ["run", "cli_file_hooks.py", "--app-dir", str(tmp_path), "--provider", "codex"]
        )

        assert exit_code == 27
        assert isinstance(captured_target, AgentHook)
        assert captured_provider == "codex"

    def test_main_callback_passes_provider(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured_target: object | None = None
        captured_provider: str | None = None

        def fake_run_callback(target: object, *, provider: str | None = None) -> int:
            nonlocal captured_target
            nonlocal captured_provider
            captured_target = target
            captured_provider = provider
            return 11

        monkeypatch.setattr("agent_hooks.cli_app.cli.run_callback", fake_run_callback)

        exit_code = cli_main(["callback", "--provider", "codex"])

        assert exit_code == 11
        assert captured_target is app
        assert captured_provider == "codex"
