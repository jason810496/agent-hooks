from __future__ import annotations

from pathlib import Path

from agent_hooks.enums import AppleScriptInvocation, DialogButton, TransportStatus
from agent_hooks.models.response import AppleScriptResult, DialogSpec
from agent_hooks.transport import AppleScriptTransport, resolve_dialog_icon_path


def test_resolve_dialog_icon_path_returns_packaged_logo() -> None:
    icon_path = Path(resolve_dialog_icon_path())

    assert icon_path.name == "osascript-logo.png"
    assert icon_path.is_file()


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
        "Deny",
        "Allow Once",
    ]
    assert "set theIconPath to item 4 of argv" in captured_script
    assert "with icon (POSIX file theIconPath)" in captured_script
    assert result.button == DialogButton.ALLOW_ONCE
