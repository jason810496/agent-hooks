"""Build the display transport for the selected ``--ui`` backend.

The framework is transport-agnostic; this module is where the built-in app maps a
``--ui`` choice to a concrete :class:`~agent_hooks.transport.DisplayTransport` and injects
it into ``run_callback``.
"""

from __future__ import annotations

from io import StringIO

from agent_hooks.config import RuntimeConfig
from agent_hooks.enums import HookProvider
from agent_hooks.parsing import read_hook_input
from agent_hooks.transport import DisplayTransport
from app.applescript.transport import AppleScriptTransport
from app.swift_ui.cleanup import install_handlers
from app.swift_ui.config import load_swift_ui_config
from app.swift_ui.db import daemon_is_alive
from app.swift_ui.transport import SQLiteTransport

APPLESCRIPT_UI = "applescript"
SWIFT_UI = "swift-ui"
UI_CHOICES = (APPLESCRIPT_UI, SWIFT_UI)
DEFAULT_UI = APPLESCRIPT_UI


def build_transport(
    ui: str,
    *,
    config: RuntimeConfig,
    raw_input: str,
    provider: HookProvider | str | None = None,
) -> DisplayTransport:
    """Return the display transport for one callback run.

    :param ui: Selected UI backend, one of :data:`UI_CHOICES`.
    :type ui: str
    :param config: Resolved framework runtime configuration (drives the AppleScript knobs).
    :type config: RuntimeConfig
    :param raw_input: Raw hook stdin, used by the swift-ui backend to parse the payload
        before building its transport. Ignored by the AppleScript backend.
    :type raw_input: str
    :param provider: Optional hook protocol provider override for payload parsing.
    :type provider: HookProvider | str | None
    :return: The transport to inject into ``run_callback``.
    """
    if ui == SWIFT_UI:
        return _build_swift_ui_transport(config=config, raw_input=raw_input, provider=provider)
    return _build_applescript_transport(config)


def _build_applescript_transport(config: RuntimeConfig) -> AppleScriptTransport:
    """Build the AppleScript transport from the framework config."""
    return AppleScriptTransport(
        skip_osascript=config.skip_osascript,
        dialog_font_size=config.dialog_font_size,
        notification_timeout=config.notification_timeout_seconds,
    )


def _build_swift_ui_transport(
    *,
    config: RuntimeConfig,
    raw_input: str,
    provider: HookProvider | str | None,
) -> DisplayTransport:
    """Build the SQLite transport, or fall back to AppleScript when no daemon runs."""
    swift_config = load_swift_ui_config()
    if not daemon_is_alive(swift_config.db_path):
        # The Swift daemon is not running: fall back to AppleScript so the hook still has
        # a UI to answer it instead of blocking on a database nobody is watching.
        return _build_applescript_transport(config)
    payload = read_hook_input(StringIO(raw_input), provider=provider).payload
    install_handlers()
    return SQLiteTransport(
        payload=payload,
        db_path=swift_config.db_path,
        poll_interval=swift_config.poll_interval_seconds,
        request_timeout=swift_config.request_timeout_seconds,
    )


__all__ = ["APPLESCRIPT_UI", "DEFAULT_UI", "SWIFT_UI", "UI_CHOICES", "build_transport"]
