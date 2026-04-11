"""Provide the installable command-line entrypoint."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from io import StringIO
from typing import IO

from agent_hooks.config import RuntimeConfig, load_runtime_config
from agent_hooks.logging_utils import (
    append_application_log,
    append_input_audit_log,
    append_response_audit_log,
)
from agent_hooks.models import (
    ApplicationLogRecord,
    HookResponse,
    InputAuditLogRecord,
    ResponseAuditLogRecord,
)
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
    stream.write(render_hook_response(response))


def render_hook_response(response: HookResponse | None = None) -> str:
    """Render the structured response JSON expected by Claude.

    :param response: Hook response to render.
    :type response: HookResponse | None
    :return: Serialized response text, including the trailing newline.
    """
    buffer = StringIO()
    json.dump((response or HookResponse()).as_payload(), buffer, separators=(",", ":"))
    buffer.write("\n")
    return buffer.getvalue()


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
    append_input_audit_log(
        InputAuditLogRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            hook_event_name=input_data.payload.raw_event_name,
            session_id=input_data.payload.session_id,
            cwd=input_data.payload.cwd,
            raw_input=input_data.raw_input,
        ),
        config.audit_logging.input_file,
    )
    display_transport = transport or AppleScriptTransport(skip_osascript=config.skip_osascript)
    result = process_hook(input_data, display_transport)
    response_text = render_hook_response(result.response)

    timestamp = datetime.now(timezone.utc).isoformat()
    append_response_audit_log(
        ResponseAuditLogRecord(
            timestamp=timestamp,
            hook_event_name=input_data.payload.raw_event_name,
            session_id=input_data.payload.session_id,
            cwd=input_data.payload.cwd,
            hook_response=response_text,
        ),
        config.audit_logging.response_file,
    )
    append_application_log(
        ApplicationLogRecord(
            timestamp=timestamp,
            hook_event_name=input_data.payload.raw_event_name,
            session_id=input_data.payload.session_id,
            cwd=input_data.payload.cwd,
            notification_type=input_data.payload.raw_notification_type,
            tool_name=input_data.payload.tool_name,
            parse_error=input_data.parse_error,
            display=result.display,
            osascript=result.transport_result,
            suppress_output=result.response.suppress_output,
            has_hook_specific_output=result.response.hook_specific_output is not None,
            raw_input_bytes=len(input_data.raw_input.encode("utf-8")),
            response_bytes=len(response_text.encode("utf-8")),
            configuration_warnings=config.warnings,
            error=result.error,
        ),
        config.application_logging,
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
