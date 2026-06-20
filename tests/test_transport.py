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
)
from agent_hooks.transport import (
    AppleScriptTransport,
    get_ask_user_question_script,
    get_dialog_script,
    get_notification_script,
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
    set buttonIndex to responseCode - 999
    if buttonIndex < 1 or buttonIndex > (count of buttonList) then
        return ""
    end if
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


def test_dialog_script_keeps_buttons_in_row_after_multiline_layout(tmp_path: Path) -> None:
    if shutil.which("osascript") is None:
        pytest.skip("osascript is not available")

    script = get_dialog_script().replace(
        """
    set responseCode to (alert's runModal()) as integer
    set buttonIndex to responseCode - 999
    if buttonIndex < 1 or buttonIndex > (count of buttonList) then
        return ""
    end if
    return "button returned:" & (item buttonIndex of buttonList)
""",
        """
    set buttonFrameSummaries to {}
    repeat with alertButton in (alert's buttons())
        set frameRect to alertButton's frame()
        set frameOrigin to item 1 of frameRect
        set frameSize to item 2 of frameRect
        set end of buttonFrameSummaries to ((alertButton's title()) as text) & ":" & (((item 1 of frameOrigin) as real) as text) & "," & (((item 2 of frameOrigin) as real) as text) & "," & (((item 1 of frameSize) as real) as text)
    end repeat
    set AppleScript's text item delimiters to "|"
    return buttonFrameSummaries as text
""",
    )
    script_path = tmp_path / "dialog-button-frames.applescript"
    script_path.write_text(script, encoding="utf-8")

    completed = subprocess.run(
        [
            "osascript",
            str(script_path),
            "Tool: Bash\nCommand:\nls\npwd\nwhoami\n" + '\n"Always Allow" to remember.',
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

    button_frames: list[tuple[float, float, float, str]] = []
    for raw_button_frame in completed.stdout.strip().split("|"):
        title, raw_frame = raw_button_frame.split(":", 1)
        x_position, y_position, width = (float(value) for value in raw_frame.split(",", 2))
        button_frames.append((x_position, y_position, width, title))
    button_frames.sort()

    assert len(button_frames) == 3
    assert {frame[1] for frame in button_frames} == {16.0}
    for current_frame, next_frame in zip(button_frames, button_frames[1:], strict=False):
        current_right = current_frame[0] + current_frame[2]
        assert current_right <= next_frame[0], completed.stdout


def test_dialog_script_centers_buttons_under_informative_text(tmp_path: Path) -> None:
    if shutil.which("osascript") is None:
        pytest.skip("osascript is not available")

    script = get_dialog_script().replace(
        """
    set responseCode to (alert's runModal()) as integer
    set buttonIndex to responseCode - 999
    if buttonIndex < 1 or buttonIndex > (count of buttonList) then
        return ""
    end if
    return "button returned:" & (item buttonIndex of buttonList)
""",
        """
    set layoutBounds to my buttonHorizontalBoundsForLayout(alert's |window|()'s contentView(), theMessage, 16)
    set layoutCenter to ((item 1 of layoutBounds) + (item 2 of layoutBounds)) / 2
    set buttonRowLeftEdge to 1000000
    set buttonRowRightEdge to 0
    repeat with alertButton in (alert's buttons())
        set frameRect to alertButton's frame()
        set frameOrigin to item 1 of frameRect
        set frameSize to item 2 of frameRect
        set buttonLeftEdge to (item 1 of frameOrigin) as real
        set buttonRightEdge to buttonLeftEdge + ((item 1 of frameSize) as real)
        if buttonLeftEdge is less than buttonRowLeftEdge then
            set buttonRowLeftEdge to buttonLeftEdge
        end if
        if buttonRightEdge is greater than buttonRowRightEdge then
            set buttonRowRightEdge to buttonRightEdge
        end if
    end repeat
    set buttonRowCenter to (buttonRowLeftEdge + buttonRowRightEdge) / 2
    return (layoutCenter as text) & "|" & (buttonRowCenter as text)
""",
    )
    script_path = tmp_path / "dialog-button-centering.applescript"
    script_path.write_text(script, encoding="utf-8")

    completed = subprocess.run(
        [
            "osascript",
            str(script_path),
            (
                "Tool: Bash\nCommand:\n"
                "git status\n"
                "asdasdasdasdasd asdasdasd asdasda\n"
                " asdasdasd asdasdasd asdasd\n"
                " asdasdas asdas\n"
                " asdasd\n"
                "asdasdddddasdasdasdsadasdsadasdasdsadasdasdasdasdasdsad asd "
                "sadasdasdasd asdasdasdasdasdasdasdasdasdasda\n"
                "asdasdasda asdasdas asdas\n"
            ),
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
    layout_center_raw, button_row_center_raw = completed.stdout.strip().split("|", 1)
    assert abs(float(layout_center_raw) - float(button_row_center_raw)) < 1, completed.stdout


def test_dialog_script_does_not_highlight_default_button(tmp_path: Path) -> None:
    if shutil.which("osascript") is None:
        pytest.skip("osascript is not available")

    script = get_dialog_script().replace(
        """
    set responseCode to (alert's runModal()) as integer
    set buttonIndex to responseCode - 999
    if buttonIndex < 1 or buttonIndex > (count of buttonList) then
        return ""
    end if
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
    assert completed.stdout.strip() == "Deny:0|Allow Once:0|Always Allow:0"


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
    responses = iter(["Jest", "AWS\n##\nGCP"])

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
