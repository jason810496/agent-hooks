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
from app.transports import DEFAULT_UI, SWIFT_UI, UI_CHOICES, build_transport


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
    if command not in {None, "callback", "run"}:
        return 0

    ui = getattr(args, "ui", DEFAULT_UI)
    provider = getattr(args, "provider", None)
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
