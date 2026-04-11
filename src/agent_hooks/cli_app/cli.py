"""Provide the installable command-line interface for the built-in app."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from agent_hooks.enums import HookProvider
from agent_hooks.runner import load_run_callback_target, run_callback

DEFAULT_CALLBACK_TARGET = "cli_app.app:app"


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    :return: Configured argument parser.
    """
    parser = argparse.ArgumentParser(description="Process agent hook callbacks.")
    subparsers = parser.add_subparsers(dest="command")

    callback_parser = subparsers.add_parser("callback", help="Run the built-in callback app.")
    callback_parser.add_argument(
        "--provider",
        choices=tuple(provider.value for provider in HookProvider),
        help="Hook protocol provider. Defaults to runtime config or claude-code.",
    )
    callback_parser.set_defaults(command="callback")

    run_parser = subparsers.add_parser(
        "run",
        help="Run a custom AgentHook app from a Python file or import string.",
    )
    run_parser.add_argument(
        "target",
        help="Python file path like 'main.py' or import string like 'main:app'.",
    )
    run_parser.add_argument(
        "--app-dir",
        default=".",
        help="Directory to add to the Python import path. Defaults to the current directory.",
    )
    run_parser.add_argument(
        "--provider",
        choices=tuple(provider.value for provider in HookProvider),
        help="Hook protocol provider. Defaults to runtime config or claude-code.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``agent-hooks`` command-line interface.

    :param argv: Optional argument list override.
    :type argv: Sequence[str] | None
    :return: Process exit code.
    """
    parser = build_argument_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command in {None, "callback"}:
        return run_callback(DEFAULT_CALLBACK_TARGET, provider=getattr(args, "provider", None))
    if args.command == "run":
        target = load_run_callback_target(args.target, app_dir=Path(args.app_dir))
        return run_callback(target, provider=args.provider)
    return 0
