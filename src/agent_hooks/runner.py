"""Provide the generic callback execution runtime."""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timezone
from io import StringIO
from types import ModuleType
from typing import IO, Protocol, TypeAlias, cast

from agent_hooks.config import RuntimeConfig, load_runtime_config
from agent_hooks.logging_utils import (
    append_application_log,
    append_input_audit_log,
    append_response_audit_log,
)
from agent_hooks.models import (
    ApplicationLogRecord,
    HookInput,
    HookProcessingResult,
    HookResponse,
    HookResponseProtocol,
    InputAuditLogRecord,
    ResponseAuditLogRecord,
)
from agent_hooks.parsing import read_hook_input
from agent_hooks.processor import process_hook
from agent_hooks.transport import AppleScriptTransport, DisplayTransport


class CallbackDispatcher(Protocol):
    """Define the callback dispatch contract used by the CLI runner."""

    def dispatch(self, input_data: HookInput, transport: DisplayTransport) -> HookProcessingResult:
        """Dispatch one parsed hook request.

        :param input_data: Parsed hook input.
        :type input_data: HookInput
        :param transport: Display transport implementation.
        :type transport: DisplayTransport
        :return: Processing result for logging and emission.
        """
        ...


class CallbackHandler(Protocol):
    """Define the direct callback contract used by the CLI runner."""

    def __call__(self, input_data: HookInput, transport: DisplayTransport) -> HookProcessingResult:
        """Process one parsed hook request directly.

        :param input_data: Parsed hook input.
        :type input_data: HookInput
        :param transport: Display transport implementation.
        :type transport: DisplayTransport
        :return: Processing result for logging and emission.
        """
        ...


CallbackTarget: TypeAlias = str | CallbackDispatcher | CallbackHandler


def emit_hook_response(
    response: HookResponseProtocol | None = None,
    stdout: IO[str] | None = None,
) -> None:
    """Emit the structured response JSON expected by Claude.

    :param response: Hook response to emit.
    :type response: HookResponseProtocol | None
    :param stdout: Optional output stream override.
    :type stdout: IO[str] | None
    """
    stream = stdout if stdout is not None else sys.stdout
    stream.write(render_hook_response(response))


def render_hook_response(response: HookResponseProtocol | None = None) -> str:
    """Render the structured response JSON expected by Claude.

    :param response: Hook response to render.
    :type response: HookResponseProtocol | None
    :return: Serialized response text, including the trailing newline.
    """
    buffer = StringIO()
    json.dump((response or HookResponse()).as_payload(), buffer, separators=(",", ":"))
    buffer.write("\n")
    return buffer.getvalue()


def run_callback(
    hook: CallbackTarget | None = None,
    *,
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
    runtime_config: RuntimeConfig | None = None,
    transport: DisplayTransport | None = None,
) -> int:
    """Process hook JSON from stdin and emit the callback response.

    :param hook: Optional callback router, direct handler, or import string.
    :type hook: CallbackTarget | None
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
    callback_target = resolve_callback_target(hook)
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
    result = dispatch_callback(callback_target, input_data, display_transport)
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


def resolve_callback_target(hook: CallbackTarget | None) -> CallbackTarget | None:
    """Resolve a callback target from an instance or import string.

    :param hook: Callback target reference.
    :type hook: CallbackTarget | None
    :return: Resolved callback target, or ``None`` when unset.
    """
    if hook is None or not isinstance(hook, str):
        return hook
    return load_callback_target(hook)


def load_callback_target(reference: str) -> CallbackTarget:
    """Load a callback target from a ``module:attribute`` reference.

    :param reference: Import reference for the callback target.
    :type reference: str
    :return: Imported callback target.
    :raises ValueError: If the reference format is invalid or the attribute is missing.
    """
    module_name, separator, attribute_name = reference.partition(":")
    if separator == "" or module_name == "" or attribute_name == "":
        raise ValueError("Callback target references must use the 'module:attribute' format.")

    module = import_callback_module(module_name)
    try:
        return getattr(module, attribute_name)
    except AttributeError as exc:
        raise ValueError(
            f"Module '{module.__name__}' does not define callback target '{attribute_name}'."
        ) from exc


def import_callback_module(module_name: str) -> ModuleType:
    """Import a callback module, preferring package-local short references.

    :param module_name: Module portion of the callback target reference.
    :type module_name: str
    :return: Imported Python module.
    :raises ModuleNotFoundError: If the module cannot be imported.
    """
    candidates = (
        (module_name,)
        if module_name.startswith("agent_hooks.")
        else (f"agent_hooks.{module_name}", module_name)
    )
    last_error: ModuleNotFoundError | None = None
    for candidate in candidates:
        try:
            return importlib.import_module(candidate)
        except ModuleNotFoundError as exc:
            if exc.name != candidate:
                raise
            last_error = exc

    assert last_error is not None
    raise last_error


def dispatch_callback(
    hook: CallbackTarget | None,
    input_data: HookInput,
    transport: DisplayTransport,
) -> HookProcessingResult:
    """Dispatch a parsed hook request through the configured callback target.

    :param hook: Callback target instance, callable, or ``None``.
    :type hook: CallbackTarget | None
    :param input_data: Parsed hook input.
    :type input_data: HookInput
    :param transport: Display transport implementation.
    :type transport: DisplayTransport
    :return: Processing result for logging and emission.
    :raises TypeError: If the callback target does not expose a supported interface.
    """
    if hook is None:
        return process_hook(input_data, transport)

    if isinstance(hook, str):
        hook = load_callback_target(hook)

    dispatcher = getattr(hook, "dispatch", None)
    if callable(dispatcher):
        return dispatcher(input_data, transport)

    if callable(hook):
        return cast(CallbackHandler, hook)(input_data, transport)

    raise TypeError(
        "Callback target must be a dispatcher instance, direct handler, or import string."
    )
