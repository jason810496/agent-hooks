from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agent_hooks.config import DEFAULT_DIALOG_FONT_SIZE
from agent_hooks.enums import AppleScriptInvocation, DialogButton, TransportStatus
from agent_hooks.models.response import AppleScriptResult, DialogSpec
from agent_hooks.transport import (
    AppleScriptTransport,
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
