"""Provide the installable command-line interface for the built-in app."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from agent_hooks.runner import run_callback

DEFAULT_CALLBACK_TARGET = "cli_app.app:app"


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    :return: Configured argument parser.
    """
    parser = argparse.ArgumentParser(description="Process agent hook callbacks.")
    parser.add_argument(
        "command",
        nargs="?",
        default="callback",
        choices=("callback",),
        help="Callback command to execute.",
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
    if args.command == "callback":
        return run_callback(DEFAULT_CALLBACK_TARGET)
    return 0
