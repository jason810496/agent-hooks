"""Provide the generic callback execution runtime."""

from __future__ import annotations

import ast
import contextlib
import importlib
import json
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
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


def load_run_callback_target(reference: str, *, app_dir: str | Path = ".") -> CallbackTarget:
    """Load a callback target for the CLI ``run`` command.

    :param reference: Import string or Python file path.
    :type reference: str
    :param app_dir: Base directory to add to ``sys.path`` for imports.
    :type app_dir: str | Path
    :return: Loaded callback target.
    """
    resolved_app_dir = Path(app_dir).resolve()
    if reference.endswith(".py"):
        module_path = Path(reference)
        if not module_path.is_absolute():
            module_path = resolved_app_dir / module_path
        return load_callback_target_from_file(module_path, app_dir=resolved_app_dir)
    return load_callback_target(reference, app_dir=resolved_app_dir)


def resolve_callback_target(hook: CallbackTarget | None) -> CallbackTarget | None:
    """Resolve a callback target from an instance or import string.

    :param hook: Callback target reference.
    :type hook: CallbackTarget | None
    :return: Resolved callback target, or ``None`` when unset.
    """
    if hook is None or not isinstance(hook, str):
        return hook
    return load_callback_target(hook)


def load_callback_target(reference: str, *, app_dir: Path | None = None) -> CallbackTarget:
    """Load a callback target from a ``module:attribute`` reference.

    :param reference: Import reference for the callback target.
    :type reference: str
    :param app_dir: Optional directory added to ``sys.path`` while importing.
    :type app_dir: Path | None
    :return: Imported callback target.
    :raises ValueError: If the reference format is invalid or the attribute is missing.
    """
    module_name, separator, attribute_name = reference.partition(":")
    if separator == "" or module_name == "" or attribute_name == "":
        raise ValueError("Callback target references must use the 'module:attribute' format.")

    module = import_callback_module(module_name, app_dir=app_dir)
    try:
        return getattr(module, attribute_name)
    except AttributeError as exc:
        raise ValueError(
            f"Module '{module.__name__}' does not define callback target '{attribute_name}'."
        ) from exc


def load_callback_target_from_file(module_path: Path, *, app_dir: Path) -> CallbackTarget:
    """Load a callback target from a Python file by discovering its app instance.

    :param module_path: Python file that defines a top-level ``AgentHook`` instance.
    :type module_path: Path
    :param app_dir: Base directory added to ``sys.path`` while importing.
    :type app_dir: Path
    :return: Imported callback target.
    :raises ValueError: If the file cannot be mapped to an importable module or no app is found.
    """
    resolved_module_path = module_path.resolve()
    module_name = module_name_from_path(resolved_module_path, app_dir=app_dir)
    attribute_name = discover_agent_hook_name(resolved_module_path)
    return load_callback_target(f"{module_name}:{attribute_name}", app_dir=app_dir)


def import_callback_module(module_name: str, *, app_dir: Path | None = None) -> ModuleType:
    """Import a callback module, preferring package-local short references.

    :param module_name: Module portion of the callback target reference.
    :type module_name: str
    :param app_dir: Optional directory added to ``sys.path`` while importing.
    :type app_dir: Path | None
    :return: Imported Python module.
    :raises ModuleNotFoundError: If the module cannot be imported.
    """
    candidates = (
        (module_name,)
        if module_name.startswith("agent_hooks.")
        else (f"agent_hooks.{module_name}", module_name)
    )
    last_error: ModuleNotFoundError | None = None
    with prepend_sys_path(app_dir):
        for candidate in candidates:
            try:
                return importlib.import_module(candidate)
            except ModuleNotFoundError as exc:
                if exc.name != candidate:
                    raise
                last_error = exc

    assert last_error is not None
    raise last_error


@contextlib.contextmanager
def prepend_sys_path(path: Path | None) -> Iterator[None]:
    """Temporarily prepend one directory to ``sys.path``.

    :param path: Directory to prepend, or ``None`` to keep ``sys.path`` unchanged.
    :type path: Path | None
    :return: Iterator used by ``contextlib.contextmanager``.
    """
    if path is None:
        yield
        return

    path_string = str(path)
    sys.path.insert(0, path_string)
    try:
        yield
    finally:
        if sys.path and sys.path[0] == path_string:
            sys.path.pop(0)
        else:
            with contextlib.suppress(ValueError):
                sys.path.remove(path_string)


def module_name_from_path(module_path: Path, *, app_dir: Path) -> str:
    """Build an importable module name for a Python file inside ``app_dir``.

    :param module_path: Python file to map to an import string.
    :type module_path: Path
    :param app_dir: Base directory that should contain the module.
    :type app_dir: Path
    :return: Importable module name.
    :raises ValueError: If the file is outside ``app_dir`` or cannot form a valid module name.
    """
    if module_path.suffix != ".py":
        raise ValueError(f"Expected a Python file, got '{module_path}'.")
    if not module_path.exists():
        raise ValueError(f"Python file '{module_path}' does not exist.")

    try:
        relative_module_path = module_path.relative_to(app_dir)
    except ValueError as exc:
        raise ValueError(
            f"Python file '{module_path}' must be inside app_dir '{app_dir}'."
        ) from exc

    module_parts = list(relative_module_path.with_suffix("").parts)
    if module_parts and module_parts[-1] == "__init__":
        module_parts.pop()
    if not module_parts:
        raise ValueError(f"Could not determine a module name for '{module_path}'.")

    invalid_parts = [part for part in module_parts if not part.isidentifier()]
    if invalid_parts:
        invalid_names = ", ".join(invalid_parts)
        raise ValueError(
            f"Python file '{module_path}' cannot be imported because these path parts are "
            f"not valid identifiers: {invalid_names}."
        )

    return ".".join(module_parts)


def discover_agent_hook_name(module_path: Path) -> str:
    """Inspect a Python file and return the discovered ``AgentHook`` instance name.

    :param module_path: Python file to inspect.
    :type module_path: Path
    :return: Top-level variable name bound to an ``AgentHook`` instance.
    :raises ValueError: If no app instance is found or multiple ambiguous instances exist.
    """
    module = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    constructor_names = collect_agent_hook_constructor_names(module)
    instance_names: list[str] = []
    for statement in module.body:
        instance_names.extend(find_agent_hook_assignment_names(statement, constructor_names))

    unique_instance_names = tuple(dict.fromkeys(instance_names))
    if not unique_instance_names:
        raise ValueError(
            f"No top-level AgentHook() instance found in '{module_path}'. "
            "Use 'module:attribute' instead."
        )
    if len(unique_instance_names) == 1:
        return unique_instance_names[0]
    if "app" in unique_instance_names:
        return "app"

    choices = ", ".join(unique_instance_names)
    raise ValueError(
        f"Multiple top-level AgentHook() instances found in '{module_path}': {choices}. "
        "Use 'module:attribute' instead."
    )


def collect_agent_hook_constructor_names(module: ast.Module) -> set[str]:
    """Collect callable names that resolve to ``AgentHook`` in one module.

    :param module: Parsed Python module.
    :type module: ast.Module
    :return: Dotted names that should be treated as ``AgentHook`` constructors.
    """
    constructor_names: set[str] = set()
    for statement in module.body:
        if isinstance(statement, ast.ImportFrom):
            if statement.module in {"agent_hooks", "agent_hooks.router"}:
                for alias in statement.names:
                    if alias.name == "AgentHook":
                        constructor_names.add(alias.asname or alias.name)
                    if statement.module == "agent_hooks" and alias.name == "router":
                        constructor_names.add(f"{alias.asname or alias.name}.AgentHook")
        elif isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.name == "agent_hooks":
                    constructor_names.add(f"{alias.asname or 'agent_hooks'}.AgentHook")
                if alias.name == "agent_hooks.router":
                    if alias.asname is not None:
                        constructor_names.add(f"{alias.asname}.AgentHook")
                    else:
                        constructor_names.add("agent_hooks.router.AgentHook")
    return constructor_names


def find_agent_hook_assignment_names(statement: ast.stmt, constructor_names: set[str]) -> list[str]:
    """Return top-level variable names assigned from an ``AgentHook`` constructor.

    :param statement: Statement to inspect.
    :type statement: ast.stmt
    :param constructor_names: Known callable names that instantiate ``AgentHook``.
    :type constructor_names: set[str]
    :return: Assigned variable names.
    """
    if isinstance(statement, ast.Assign):
        value = statement.value
        targets = statement.targets
    elif isinstance(statement, ast.AnnAssign):
        value = statement.value
        targets = [statement.target]
    else:
        return []

    if value is None or not is_agent_hook_constructor_call(value, constructor_names):
        return []

    assignment_names: list[str] = []
    for target in targets:
        assignment_names.extend(extract_assignment_names(target))
    return assignment_names


def is_agent_hook_constructor_call(node: ast.AST, constructor_names: set[str]) -> bool:
    """Return whether one AST node instantiates ``AgentHook``.

    :param node: AST node to inspect.
    :type node: ast.AST
    :param constructor_names: Known callable names that instantiate ``AgentHook``.
    :type constructor_names: set[str]
    :return: ``True`` when the node is a matching constructor call.
    """
    if not isinstance(node, ast.Call):
        return False

    dotted_name = render_dotted_name(node.func)
    return dotted_name in constructor_names


def render_dotted_name(node: ast.AST) -> str | None:
    """Render an AST name or attribute chain into dotted text.

    :param node: AST node to render.
    :type node: ast.AST
    :return: Dotted name, or ``None`` when the node is not a simple name chain.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base_name = render_dotted_name(node.value)
        if base_name is None:
            return None
        return f"{base_name}.{node.attr}"
    return None


def extract_assignment_names(node: ast.AST) -> list[str]:
    """Extract variable names from an assignment target.

    :param node: Assignment target node.
    :type node: ast.AST
    :return: Variable names bound by the assignment.
    """
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Tuple | ast.List):
        names: list[str] = []
        for element in node.elts:
            names.extend(extract_assignment_names(element))
        return names
    return []


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
