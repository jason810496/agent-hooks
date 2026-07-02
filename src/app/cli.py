"""Provide the installable command-line interface for the built-in app."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from io import StringIO
from pathlib import Path

from agent_hooks.config import load_runtime_config
from agent_hooks.enums import HookProvider
from agent_hooks.runner import AgentHookFileLoader, run_callback
from app.builtin import app as builtin_app
from app.remote.client import forward_remote
from app.remote.server import run_server_command
from app.transports import DEFAULT_UI, REMOTE_UI, SWIFT_UI, UI_CHOICES, build_transport


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--ui`` and ``--provider`` options to a subparser.

    :param parser: Subparser to extend.
    :type parser: argparse.ArgumentParser
    """
    parser.add_argument(
        "--ui",
        choices=UI_CHOICES,
        default=DEFAULT_UI,
        help="Local UI backend used to answer hook events. Defaults to 'applescript'.",
    )
    parser.add_argument(
        "--provider",
        choices=tuple(provider.value for provider in HookProvider),
        help="Hook protocol provider. Defaults to runtime config or claude-code.",
    )


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    :return: Configured argument parser.
    """
    parser = argparse.ArgumentParser(description="Process agent hook callbacks.")
    subparsers = parser.add_subparsers(dest="command")

    callback_parser = subparsers.add_parser("callback", help="Run the built-in callback app.")
    _add_common_arguments(callback_parser)
    callback_parser.set_defaults(command="callback")

    run_parser = subparsers.add_parser(
        "run",
        help="Run a custom AgentHook app from a Python file.",
    )
    run_parser.add_argument(
        "target",
        help="Python file path like 'main.py' containing a top-level AgentHook instance.",
    )
    run_parser.add_argument(
        "--app-dir",
        default=".",
        help="Directory to add to the Python import path. Defaults to the current directory.",
    )
    _add_common_arguments(run_parser)

    server_parser = subparsers.add_parser(
        "server",
        help="Run the remote hook broker (TCP) on the host for containerized clients.",
    )
    server_parser.add_argument(
        "action",
        choices=("start", "stop", "status"),
        help="Start, stop, or query the broker.",
    )
    server_parser.add_argument(
        "--host",
        default=None,
        help="Bind address. Defaults to $AGENT_HOOK_SERVER_HOST or 127.0.0.1.",
    )
    server_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port. Defaults to $AGENT_HOOK_SERVER_PORT or 48373.",
    )
    server_parser.add_argument(
        "--token",
        default=None,
        help="Shared secret clients must present. Defaults to $AGENT_HOOK_SERVER_TOKEN.",
    )
    server_parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run in the foreground instead of detaching (used internally / for launchd).",
    )
    server_parser.set_defaults(command="server")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``agent-hooks`` command-line interface.

    :param argv: Optional argument list override.
    :type argv: Sequence[str] | None
    :return: Process exit code.
    """
    parser = build_argument_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    command = args.command

    if command == "server":
        return run_server_command(args)

    if command not in {None, "callback", "run"}:
        return 0

    ui = getattr(args, "ui", DEFAULT_UI)
    provider = getattr(args, "provider", None)

    # The remote backend forwards the raw hook to a host-side ``agent-hooks server`` instead
    # of building a local transport. Read stdin and hand it over; nothing else runs here.
    if ui == REMOTE_UI:
        return forward_remote(sys.stdin.read(), provider)

    config = load_runtime_config()

    if command == "run":
        hook = AgentHookFileLoader(app_dir=Path(args.app_dir)).load(args.target)
    else:
        hook = builtin_app

    # The swift-ui backend needs the parsed payload to build its transport, so read
    # stdin here and replay it into run_callback. The AppleScript backend does not, so
    # leave stdin for run_callback to read as before.
    if ui == SWIFT_UI:
        raw_input = sys.stdin.read()
        transport = build_transport(ui, config=config, raw_input=raw_input, provider=provider)
        return run_callback(
            hook, stdin=StringIO(raw_input), transport=transport, provider=provider
        )

    transport = build_transport(ui, config=config, raw_input="", provider=provider)
    return run_callback(hook, transport=transport, provider=provider)
