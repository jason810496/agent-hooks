"""Provide the installable command-line entrypoint."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import IO

from agent_hooks.config import RuntimeConfig, load_runtime_config
from agent_hooks.logging_utils import append_log, append_raw_input_log
from agent_hooks.models import HookLogRecord, HookResponse
from agent_hooks.parsing import read_hook_input
from agent_hooks.processor import process_hook
from agent_hooks.transport import AppleScriptTransport, DisplayTransport


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


def emit_hook_response(response: HookResponse | None = None, stdout: IO[str] | None = None) -> None:
    """Emit the structured response JSON expected by Claude.

    :param response: Hook response to emit.
    :type response: HookResponse | None
    :param stdout: Optional output stream override.
    :type stdout: IO[str] | None
    """
    stream = stdout if stdout is not None else sys.stdout
    json.dump((response or HookResponse()).as_payload(), stream, separators=(",", ":"))
    stream.write("\n")


def run_callback(
    *,
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
    runtime_config: RuntimeConfig | None = None,
    transport: DisplayTransport | None = None,
) -> int:
    """Process hook JSON from stdin and emit the callback response.

    :param stdin: Optional stdin override.
    :type stdin: IO[str] | None
    :param stdout: Optional stdout override.
    :type stdout: IO[str] | None
    :param runtime_config: Optional runtime configuration override.
    :type runtime_config: RuntimeConfig | None
    :param transport: Optional UI transport override.
    :type transport: DisplayTransport | None
    :return: Process exit code.
    """
    config = runtime_config or load_runtime_config()
    input_data = read_hook_input(stdin)
    display_transport = transport or AppleScriptTransport(skip_osascript=config.skip_osascript)
    result = process_hook(input_data, display_transport)
    timestamp = datetime.now(timezone.utc).isoformat()

    append_raw_input_log(
        timestamp=timestamp,
        payload=input_data.payload,
        raw_input=input_data.raw_input,
        path=config.raw_log_path,
    )
    append_log(
        HookLogRecord(
            timestamp=timestamp,
            log_path=config.log_path,
            raw_log_path=config.raw_log_path,
            raw_input=input_data.raw_input,
            hook_event_name=input_data.payload.raw_event_name,
            payload=input_data.payload.raw,
            display=result.display,
            osascript=result.transport_result,
            hook_response=result.response.as_payload(),
            error=result.error,
        )
    )
    emit_hook_response(result.response, stdout=stdout)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``agent-hooks`` command-line interface.

    :param argv: Optional argument list override.
    :type argv: Sequence[str] | None
    :return: Process exit code.
    """
    parser = build_argument_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "callback":
        return run_callback()
    return 0
