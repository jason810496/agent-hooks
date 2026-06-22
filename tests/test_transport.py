from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agent_hooks.config import DEFAULT_DIALOG_FONT_SIZE, DEFAULT_NOTIFICATION_TIMEOUT_SECONDS
from agent_hooks.enums import (
    AppleScriptInvocation,
    DialogButton,
    NotificationSound,
    TransportStatus,
)
from agent_hooks.models.response import AppleScriptResult, DialogSpec, NotificationSpec
from agent_hooks.models.schemas.display import (
    AskUserQuestionDialogSpec,
    AskUserQuestionEntry,
    AskUserQuestionOption,
    PermissionChoice,
    PermissionChoiceDialogSpec,
)
from agent_hooks.transport import (
    AppleScriptTransport,
    get_ask_user_question_script,
    get_dialog_script,
    get_notification_script,
    get_permission_choice_script,
    resolve_dialog_icon_path,
)


def test_resolve_dialog_icon_path_returns_packaged_logo() -> None:
    icon_path = Path(resolve_dialog_icon_path())

    assert icon_path.name == "osascript-logo.png"
    assert icon_path.is_file()


def test_script_getters_load_packaged_sources_from_cache() -> None:
    get_dialog_script.cache_clear()
    get_notification_script.cache_clear()

    dialog_script = get_dialog_script()
    notification_script = get_notification_script()

    assert dialog_script is get_dialog_script()
    assert notification_script is get_notification_script()
    assert 'use framework "AppKit"' in dialog_script
    assert "display notification" in notification_script


def test_dialog_script_sizes_width_from_longest_visible_line() -> None:
    dialog_script = get_dialog_script()

    assert "setAlertWidthForVisibleLines" in dialog_script
    assert "longestVisibleLineWidth" in dialog_script
    assert "set visibleLines to text items of textValue" in dialog_script


def test_dialog_script_compiles_on_macos(tmp_path: Path) -> None:
    if shutil.which("osacompile") is None:
        pytest.skip("osacompile is not available")

    script_path = tmp_path / "dialog.applescript"
    compiled_path = tmp_path / "dialog.scpt"
    script_path.write_text(get_dialog_script(), encoding="utf-8")

    completed = subprocess.run(
        ["osacompile", "-o", str(compiled_path), str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_dialog_script_sets_font_without_showing_dialog(tmp_path: Path) -> None:
    if shutil.which("osascript") is None:
        pytest.skip("osascript is not available")

    script = get_dialog_script().replace(
        """
    set responseCode to (alert's runModal()) as integer
    -- Buttons were added in reverse, so map the return code back to buttonList.
    set addedIndex to responseCode - 999
    if addedIndex < 1 or addedIndex > (count of buttonList) then
        return ""
    end if
    set buttonIndex to (count of buttonList) - addedIndex + 1
    return "button returned:" & (item buttonIndex of buttonList)
""",
        """
    set fontSizes to {}
    set commandFontSummaries to {}
    my collectTextFieldAttributedFontSizes(alert's |window|()'s contentView(), fontSizes)
    my collectCommandBlockFontSummaries(alert's |window|()'s contentView(), commandFontSummaries)
    set AppleScript's text item delimiters to ","
    set textFieldSummary to fontSizes as text
    set commandFontSummary to commandFontSummaries as text
    return textFieldSummary & "|" & commandFontSummary
""",
    )
    script += """

on collectTextFieldAttributedFontSizes(parentView, fontSizes)
    repeat with childView in (parentView's subviews())
        if ((childView's isKindOfClass:(current application's NSTextField)) as boolean) then
            set fontObject to (childView's attributedStringValue()'s attribute:(current application's NSFontAttributeName) atIndex:0 effectiveRange:(missing value))
            set end of fontSizes to ((fontObject's pointSize()) as text)
        end if
        my collectTextFieldAttributedFontSizes(childView, fontSizes)
    end repeat
end collectTextFieldAttributedFontSizes

on collectCommandBlockFontSummaries(parentView, commandFontSummaries)
    repeat with childView in (parentView's subviews())
        if ((childView's isKindOfClass:(current application's NSTextField)) as boolean) then
            set textNSString to current application's NSString's stringWithString:(childView's stringValue())
            set commandLabelRange to textNSString's rangeOfString:"Command:"
            if (commandLabelRange's |length| as integer) > 0 then
                set commandStart to (commandLabelRange's location as integer) + (commandLabelRange's |length| as integer)
                set messageLength to textNSString's |length|()
                repeat while commandStart < messageLength
                    set characterRange to current application's NSMakeRange(commandStart, 1)
                    set currentCharacter to (textNSString's substringWithRange:characterRange) as text
                    if currentCharacter is " " or currentCharacter is linefeed then
                        set commandStart to commandStart + 1
                    else
                        exit repeat
                    end if
                end repeat
                set fontObject to (childView's attributedStringValue()'s attribute:(current application's NSFontAttributeName) atIndex:commandStart effectiveRange:(missing value))
                set end of commandFontSummaries to ((fontObject's pointSize()) as text) & ":" & ((fontObject's isFixedPitch()) as text)
            end if
        end if
        my collectCommandBlockFontSummaries(childView, commandFontSummaries)
    end repeat
end collectCommandBlockFontSummaries
"""
    script_path = tmp_path / "dialog-no-modal.applescript"
    script_path.write_text(script, encoding="utf-8")

    completed = subprocess.run(
        [
            "osascript",
            str(script_path),
            "Tool: Bash\nCommand:\npython3 - <<'PY'\nprint(1)\nPY",
            "Permission Request",
            DialogButton.ALLOW_ONCE.value,
            "",
            "18",
            DialogButton.DENY.value,
            DialogButton.ALLOW_ONCE.value,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "18.0,18.0|18.0:true"


def test_dialog_script_does_not_highlight_default_button(tmp_path: Path) -> None:
    if shutil.which("osascript") is None:
        pytest.skip("osascript is not available")

    script = get_dialog_script().replace(
        """
    set responseCode to (alert's runModal()) as integer
    -- Buttons were added in reverse, so map the return code back to buttonList.
    set addedIndex to responseCode - 999
    if addedIndex < 1 or addedIndex > (count of buttonList) then
        return ""
    end if
    set buttonIndex to (count of buttonList) - addedIndex + 1
    return "button returned:" & (item buttonIndex of buttonList)
""",
        """
    set keyEquivalentSummaries to {}
    repeat with alertButton in (alert's buttons())
        set keyValue to (alertButton's keyEquivalent()) as text
        set keyNSString to current application's NSString's stringWithString:keyValue
        set end of keyEquivalentSummaries to ((alertButton's title()) as text) & ":" & ((keyNSString's |length|()) as integer as text)
    end repeat
    set AppleScript's text item delimiters to "|"
    return keyEquivalentSummaries as text
""",
    )
    script_path = tmp_path / "dialog-key-equivalents.applescript"
    script_path.write_text(script, encoding="utf-8")

    completed = subprocess.run(
        [
            "osascript",
            str(script_path),
            "Tool: Bash\nCommand:\nls",
            "Permission Request",
            DialogButton.ALLOW_ONCE.value,
            "",
            "18",
            DialogButton.DENY.value,
            DialogButton.ALLOW_ONCE.value,
            DialogButton.ALWAYS_ALLOW.value,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    # NSAlert returns buttons in added order, which is reversed from buttonList so the
    # on-screen left-to-right order matches. The assertion is that none carries a key
    # equivalent (no highlighted default button).
    assert completed.stdout.strip() == "Always Allow:0|Allow Once:0|Deny:0"


def test_show_dialog_passes_custom_icon_path_to_osascript(monkeypatch) -> None:
    transport = AppleScriptTransport(skip_osascript=False)
    captured_invocation: AppleScriptInvocation | None = None
    captured_arguments: list[str] | None = None
    captured_script = ""

    def fake_run_osascript(
        *,
        invocation: AppleScriptInvocation,
        arguments: list[str],
        script: str,
    ) -> AppleScriptResult:
        nonlocal captured_invocation, captured_arguments, captured_script
        captured_invocation = invocation
        captured_arguments = arguments
        captured_script = script
        return AppleScriptResult(
            status=TransportStatus.SUCCEEDED,
            invocation=invocation,
            stdout="button returned:Allow Once",
        )

    monkeypatch.setattr("agent_hooks.transport.resolve_dialog_icon_path", lambda: "/tmp/logo.jpeg")
    monkeypatch.setattr(transport, "_run_osascript", fake_run_osascript)

    result = transport.show_dialog(
        DialogSpec(
            title="Permission Request",
            message="Run command?",
            buttons=(DialogButton.DENY, DialogButton.ALLOW_ONCE),
            default_button=DialogButton.ALLOW_ONCE,
        )
    )

    assert captured_invocation == AppleScriptInvocation.DIALOG
    assert captured_arguments == [
        "Run command?",
        "Permission Request",
        "Allow Once",
        "/tmp/logo.jpeg",
        str(DEFAULT_DIALOG_FONT_SIZE),
        "Deny",
        "Allow Once",
    ]
    assert 'use framework "AppKit"' in captured_script
    assert "set theIconPath to item 4 of argv" in captured_script
    assert "set theFontSize to (item 5 of argv) as real" in captured_script
    assert result.button == DialogButton.ALLOW_ONCE


def test_show_dialog_passes_configured_font_size_to_osascript(monkeypatch) -> None:
    transport = AppleScriptTransport(skip_osascript=False, dialog_font_size=18)
    captured_invocation: AppleScriptInvocation | None = None
    captured_arguments: list[str] | None = None
    captured_script = ""

    def fake_run_osascript(
        *,
        invocation: AppleScriptInvocation,
        arguments: list[str],
        script: str,
    ) -> AppleScriptResult:
        nonlocal captured_invocation, captured_arguments, captured_script
        captured_invocation = invocation
        captured_arguments = arguments
        captured_script = script
        return AppleScriptResult(
            status=TransportStatus.SUCCEEDED,
            invocation=invocation,
            stdout="button returned:Allow Once",
        )

    monkeypatch.setattr("agent_hooks.transport.resolve_dialog_icon_path", lambda: "/tmp/logo.jpeg")
    monkeypatch.setattr(transport, "_run_osascript", fake_run_osascript)

    result = transport.show_dialog(
        DialogSpec(
            title="Permission Request",
            message="Run command?",
            buttons=(DialogButton.DENY, DialogButton.ALLOW_ONCE),
            default_button=DialogButton.ALLOW_ONCE,
        )
    )

    assert captured_invocation == AppleScriptInvocation.DIALOG
    assert captured_arguments == [
        "Run command?",
        "Permission Request",
        "Allow Once",
        "/tmp/logo.jpeg",
        "18",
        "Deny",
        "Allow Once",
    ]
    assert 'use framework "AppKit"' in captured_script
    assert "set theFontSize to (item 5 of argv) as real" in captured_script
    assert "setSubviewFontSize" in captured_script
    assert result.button == DialogButton.ALLOW_ONCE


def test_show_dialog_prefers_dialog_font_size_over_transport_default(monkeypatch) -> None:
    transport = AppleScriptTransport(skip_osascript=False, dialog_font_size=18)
    captured_arguments: list[str] | None = None

    def fake_run_osascript(
        *,
        invocation: AppleScriptInvocation,
        arguments: list[str],
        script: str,
    ) -> AppleScriptResult:
        nonlocal captured_arguments
        captured_arguments = arguments
        return AppleScriptResult(
            status=TransportStatus.SUCCEEDED,
            invocation=invocation,
            stdout="button returned:Allow Once",
        )

    monkeypatch.setattr(transport, "_run_osascript", fake_run_osascript)

    transport.show_dialog(
        DialogSpec(
            title="Permission Request",
            message="Run command?",
            buttons=(DialogButton.DENY, DialogButton.ALLOW_ONCE),
            default_button=DialogButton.ALLOW_ONCE,
            font_size=24,
        )
    )

    assert captured_arguments is not None
    assert captured_arguments[4] == "24"


def test_ask_user_question_script_compiles_on_macos(tmp_path: Path) -> None:
    if shutil.which("osacompile") is None:
        pytest.skip("osacompile is not available")

    script_path = tmp_path / "ask_user_question.applescript"
    compiled_path = tmp_path / "ask_user_question.scpt"
    script_path.write_text(get_ask_user_question_script(), encoding="utf-8")

    completed = subprocess.run(
        ["osacompile", "-o", str(compiled_path), str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_show_ask_user_question_dialog_collects_single_and_multi_answers(monkeypatch) -> None:
    transport = AppleScriptTransport(skip_osascript=False)
    captured_calls: list[list[str]] = []
    # The picker returns 1-based option indices: Jest is option 1; AWS/GCP are 1 and 2.
    responses = iter(["OK\n1", "OK\n1\n2"])

    def fake_run_osascript(
        *,
        invocation: AppleScriptInvocation,
        arguments: list[str],
        script: str,
    ) -> AppleScriptResult:
        captured_calls.append(arguments)
        return AppleScriptResult(
            status=TransportStatus.SUCCEEDED,
            invocation=invocation,
            stdout=next(responses),
        )

    monkeypatch.setattr(transport, "_run_osascript", fake_run_osascript)

    dialog = AskUserQuestionDialogSpec(
        title="Claude Code",
        questions=(
            AskUserQuestionEntry(
                question="Pick a framework",
                header="Testing",
                multi_select=False,
                options=(
                    AskUserQuestionOption(label="Jest", description="Fast"),
                    AskUserQuestionOption(label="Vitest", description="Modern"),
                ),
            ),
            AskUserQuestionEntry(
                question="Pick deployments",
                header="Deploy",
                multi_select=True,
                options=(
                    AskUserQuestionOption(label="AWS"),
                    AskUserQuestionOption(label="GCP"),
                ),
            ),
        ),
    )

    result = transport.show_ask_user_question_dialog(dialog)

    assert result.answers == {
        "Pick a framework": "Jest",
        "Pick deployments": "AWS, GCP",
    }
    assert captured_calls[0][:4] == [
        "Testing",
        "Pick a framework\n\n- Jest: Fast\n- Vitest: Modern",
        "0",
        "Jest",
    ]
    assert captured_calls[0][4:] == ["Jest", "Vitest"]
    assert captured_calls[1][:4] == ["Deploy", "Pick deployments", "1", "AWS"]
    assert captured_calls[1][4:] == ["AWS", "GCP"]


def test_show_ask_user_question_dialog_accepts_sentinel_like_labels(monkeypatch) -> None:
    transport = AppleScriptTransport(skip_osascript=False)

    def fake_run_osascript(
        *,
        invocation: AppleScriptInvocation,
        arguments: list[str],
        script: str,
    ) -> AppleScriptResult:
        # The only option (label "CANCELLED") is selected, returned as index 1.
        return AppleScriptResult(
            status=TransportStatus.SUCCEEDED,
            invocation=invocation,
            stdout="OK\n1",
        )

    monkeypatch.setattr(transport, "_run_osascript", fake_run_osascript)

    result = transport.show_ask_user_question_dialog(
        AskUserQuestionDialogSpec(
            title="Claude Code",
            questions=(
                AskUserQuestionEntry(
                    question="Pick one",
                    header="Pick",
                    multi_select=False,
                    options=(AskUserQuestionOption(label="CANCELLED"),),
                ),
            ),
        )
    )

    # A selected label that equals the cancel sentinel must be injected, not treated
    # as a cancellation.
    assert result.answers == {"Pick one": "CANCELLED"}


def test_show_ask_user_question_dialog_reports_cancellation(monkeypatch) -> None:
    transport = AppleScriptTransport(skip_osascript=False)

    def fake_run_osascript(
        *,
        invocation: AppleScriptInvocation,
        arguments: list[str],
        script: str,
    ) -> AppleScriptResult:
        return AppleScriptResult(
            status=TransportStatus.SUCCEEDED,
            invocation=invocation,
            stdout="CANCELLED",
        )

    monkeypatch.setattr(transport, "_run_osascript", fake_run_osascript)

    result = transport.show_ask_user_question_dialog(
        AskUserQuestionDialogSpec(
            title="Claude Code",
            questions=(
                AskUserQuestionEntry(
                    question="Pick one",
                    header="Pick",
                    multi_select=False,
                    options=(AskUserQuestionOption(label="A"),),
                ),
            ),
        )
    )

    assert result.cancelled is True
    assert result.answers is None
    assert result.transport.status == TransportStatus.SUCCEEDED


def test_show_ask_user_question_dialog_marks_script_error_as_failed(monkeypatch) -> None:
    transport = AppleScriptTransport(skip_osascript=False)

    def fake_run_osascript(
        *,
        invocation: AppleScriptInvocation,
        arguments: list[str],
        script: str,
    ) -> AppleScriptResult:
        return AppleScriptResult(
            status=TransportStatus.SUCCEEDED,
            invocation=invocation,
            returncode=0,
            stdout="ERROR:-128:User cancelled.",
        )

    monkeypatch.setattr(transport, "_run_osascript", fake_run_osascript)

    result = transport.show_ask_user_question_dialog(
        AskUserQuestionDialogSpec(
            title="Claude Code",
            questions=(
                AskUserQuestionEntry(
                    question="Pick one",
                    header="Pick",
                    multi_select=False,
                    options=(AskUserQuestionOption(label="A"),),
                ),
            ),
        )
    )

    # A script-reported error must surface as a transport failure (not a cancellation)
    # so the caller falls back instead of denying.
    assert result.answers is None
    assert result.transport.status == TransportStatus.FAILED
    assert "ERROR:" in result.transport.stderr


def _permission_choice_spec() -> PermissionChoiceDialogSpec:
    return PermissionChoiceDialogSpec(
        title="Claude Code — Permission Request",
        message="Tool: Bash\nCommand: git status",
        choices=(
            PermissionChoice(label="Allow once", button=DialogButton.ALLOW_ONCE),
            PermissionChoice(
                label="Bash(git status)",
                button=DialogButton.ALWAYS_ALLOW,
                suggestion_index=0,
            ),
            PermissionChoice(
                label="Bash(git *)",
                button=DialogButton.ALWAYS_ALLOW,
                suggestion_index=1,
            ),
        ),
        default_index=0,
    )


def test_permission_choice_script_compiles_on_macos(tmp_path: Path) -> None:
    if shutil.which("osacompile") is None:
        pytest.skip("osacompile is not available")

    script_path = tmp_path / "permission_choice.applescript"
    compiled_path = tmp_path / "permission_choice.scpt"
    script_path.write_text(get_permission_choice_script(), encoding="utf-8")

    completed = subprocess.run(
        ["osacompile", "-o", str(compiled_path), str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_show_permission_choice_dialog_returns_selected_choice(monkeypatch) -> None:
    transport = AppleScriptTransport(skip_osascript=False)
    captured_arguments: list[str] | None = None

    def fake_run_osascript(
        *,
        invocation: AppleScriptInvocation,
        arguments: list[str],
        script: str,
    ) -> AppleScriptResult:
        nonlocal captured_arguments
        captured_arguments = arguments
        # The picker returns the selected option's 1-based index behind an "OK" line.
        return AppleScriptResult(
            status=TransportStatus.SUCCEEDED,
            invocation=invocation,
            stdout="OK\n3",
        )

    monkeypatch.setattr(transport, "_run_osascript", fake_run_osascript)

    result = transport.show_permission_choice_dialog(_permission_choice_spec())

    assert captured_arguments == [
        "Claude Code — Permission Request",
        "Tool: Bash\nCommand: git status",
        "Allow once",
        "Allow once",
        "Bash(git status)",
        "Bash(git *)",
    ]
    assert result.choice is not None
    assert result.choice.button == DialogButton.ALWAYS_ALLOW
    assert result.choice.suggestion_index == 1
    assert result.cancelled is False


def test_show_permission_choice_dialog_reports_dismissal(monkeypatch) -> None:
    transport = AppleScriptTransport(skip_osascript=False)

    def fake_run_osascript(
        *,
        invocation: AppleScriptInvocation,
        arguments: list[str],
        script: str,
    ) -> AppleScriptResult:
        return AppleScriptResult(
            status=TransportStatus.SUCCEEDED,
            invocation=invocation,
            stdout="CANCELLED",
        )

    monkeypatch.setattr(transport, "_run_osascript", fake_run_osascript)

    result = transport.show_permission_choice_dialog(_permission_choice_spec())

    assert result.cancelled is True
    assert result.choice is None
    assert result.transport.status == TransportStatus.SUCCEEDED


def test_show_permission_choice_dialog_marks_out_of_range_index_as_failed(monkeypatch) -> None:
    transport = AppleScriptTransport(skip_osascript=False)

    def fake_run_osascript(
        *,
        invocation: AppleScriptInvocation,
        arguments: list[str],
        script: str,
    ) -> AppleScriptResult:
        return AppleScriptResult(
            status=TransportStatus.SUCCEEDED,
            invocation=invocation,
            stdout="OK\n9",
        )

    monkeypatch.setattr(transport, "_run_osascript", fake_run_osascript)

    result = transport.show_permission_choice_dialog(_permission_choice_spec())

    # An "OK" status with an out-of-range index is corrupted output, not a dismissal.
    # It must surface as a transport failure so the caller falls back to the standard
    # dialog instead of silently denying the request.
    assert result.choice is None
    assert result.transport.status == TransportStatus.FAILED
    assert "unparseable picker index" in result.transport.stderr


def test_show_permission_choice_dialog_marks_script_error_as_failed(monkeypatch) -> None:
    transport = AppleScriptTransport(skip_osascript=False)

    def fake_run_osascript(
        *,
        invocation: AppleScriptInvocation,
        arguments: list[str],
        script: str,
    ) -> AppleScriptResult:
        return AppleScriptResult(
            status=TransportStatus.SUCCEEDED,
            invocation=invocation,
            returncode=0,
            stdout="ERROR:-128:User cancelled.",
        )

    monkeypatch.setattr(transport, "_run_osascript", fake_run_osascript)

    result = transport.show_permission_choice_dialog(_permission_choice_spec())

    # A script-reported error must surface as a transport failure (not a dismissal) so
    # the caller falls back to the standard dialog instead of denying.
    assert result.choice is None
    assert result.transport.status == TransportStatus.FAILED
    assert "ERROR:" in result.transport.stderr


def test_show_dialog_returns_no_button_for_empty_marker(monkeypatch) -> None:
    transport = AppleScriptTransport(skip_osascript=False)

    def fake_run_osascript(
        *,
        invocation: AppleScriptInvocation,
        arguments: list[str],
        script: str,
    ) -> AppleScriptResult:
        # Marker present but no label after it must not raise IndexError.
        return AppleScriptResult(
            status=TransportStatus.SUCCEEDED,
            invocation=invocation,
            stdout="button returned:",
        )

    monkeypatch.setattr(transport, "_run_osascript", fake_run_osascript)

    result = transport.show_dialog(
        DialogSpec(
            title="Permission Request",
            message="Run command?",
            buttons=(DialogButton.DENY, DialogButton.ALLOW_ONCE),
            default_button=DialogButton.ALLOW_ONCE,
        )
    )

    assert result.button is None


def test_send_notification_passes_configured_timeout(monkeypatch) -> None:
    transport = AppleScriptTransport(skip_osascript=False, notification_timeout=3.5)
    captured: dict[str, object] = {}

    def fake_run_osascript(
        *,
        invocation: AppleScriptInvocation,
        arguments: list[str],
        script: str,
        timeout: float | None = None,
    ) -> AppleScriptResult:
        captured["invocation"] = invocation
        captured["timeout"] = timeout
        return AppleScriptResult(status=TransportStatus.SUCCEEDED, invocation=invocation)

    monkeypatch.setattr(transport, "_run_osascript", fake_run_osascript)

    transport.send_notification(
        NotificationSpec(title="Claude finished", message="Done", sound=NotificationSound.GLASS)
    )

    assert captured["invocation"] == AppleScriptInvocation.NOTIFICATION
    assert captured["timeout"] == 3.5


def test_send_notification_defaults_to_packaged_timeout() -> None:
    transport = AppleScriptTransport(skip_osascript=False)

    assert transport._notification_timeout == DEFAULT_NOTIFICATION_TIMEOUT_SECONDS


def test_send_notification_returns_failed_result_when_osascript_times_out(monkeypatch) -> None:
    transport = AppleScriptTransport(skip_osascript=False, notification_timeout=0.01)
    monkeypatch.setattr(transport, "_build_skip_result", lambda invocation: None)
    monkeypatch.setattr(transport, "_binary", "/usr/bin/osascript")

    def fake_run(*args, **kwargs) -> None:
        raise subprocess.TimeoutExpired(cmd="osascript", timeout=0.01)

    monkeypatch.setattr("agent_hooks.transport.subprocess.run", fake_run)

    result = transport.send_notification(NotificationSpec(title="Claude finished", message="Done"))

    assert result.status == TransportStatus.FAILED
    assert result.invocation == AppleScriptInvocation.NOTIFICATION
    assert "timed out" in result.stderr


def test_show_dialog_does_not_apply_timeout(monkeypatch) -> None:
    transport = AppleScriptTransport(skip_osascript=False, notification_timeout=0.01)
    captured: dict[str, object] = {}

    def fake_run_osascript(
        *,
        invocation: AppleScriptInvocation,
        arguments: list[str],
        script: str,
        timeout: float | None = None,
    ) -> AppleScriptResult:
        captured["timeout"] = timeout
        return AppleScriptResult(
            status=TransportStatus.SUCCEEDED,
            invocation=invocation,
            stdout="button returned:Allow Once",
        )

    monkeypatch.setattr(transport, "_run_osascript", fake_run_osascript)

    transport.show_dialog(
        DialogSpec(
            title="Permission Request",
            message="Run command?",
            buttons=(DialogButton.DENY, DialogButton.ALLOW_ONCE),
            default_button=DialogButton.ALLOW_ONCE,
        )
    )

    assert captured["timeout"] is None


def test_show_dialog_uses_default_font_size_for_invalid_override(monkeypatch) -> None:
    transport = AppleScriptTransport(skip_osascript=False, dialog_font_size=-1)
    captured_arguments: list[str] | None = None

    def fake_run_osascript(
        *,
        invocation: AppleScriptInvocation,
        arguments: list[str],
        script: str,
    ) -> AppleScriptResult:
        nonlocal captured_arguments
        captured_arguments = arguments
        return AppleScriptResult(
            status=TransportStatus.SUCCEEDED,
            invocation=invocation,
            stdout="button returned:Allow Once",
        )

    monkeypatch.setattr(transport, "_run_osascript", fake_run_osascript)

    transport.show_dialog(
        DialogSpec(
            title="Permission Request",
            message="Run command?",
            buttons=(DialogButton.DENY, DialogButton.ALLOW_ONCE),
            default_button=DialogButton.ALLOW_ONCE,
        )
    )

    assert captured_arguments is not None
    assert captured_arguments[4] == str(DEFAULT_DIALOG_FONT_SIZE)
