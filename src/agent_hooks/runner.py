"""Provide the callback execution runtime for ``AgentHook`` apps."""

from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib
import importlib.util
import json
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from types import ModuleType
from typing import IO, TYPE_CHECKING

from agent_hooks.config import RuntimeConfig, load_runtime_config, use_runtime_config
from agent_hooks.enums import HookProvider
from agent_hooks.logging_utils import (
    append_application_log,
    append_input_audit_log,
    append_response_audit_log,
)
from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.models.schemas.log_records import (
    ApplicationLogRecord,
    InputAuditLogRecord,
    ResponseAuditLogRecord,
)
from agent_hooks.models.schemas.responses import HookResponse, HookResponseProtocol
from agent_hooks.parsing import read_hook_input
from agent_hooks.providers import provider_client
from agent_hooks.transport import DisplayTransport, NoopDisplayTransport

if TYPE_CHECKING:
    from agent_hooks.router import AgentHook


class AgentHookFileLoader:
    """Load an ``AgentHook`` instance from a Python file."""

    def __init__(self, *, app_dir: str | Path = ".") -> None:
        """Initialize the loader.

        :param app_dir: Base directory used to resolve relative Python file paths.
        :type app_dir: str | Path
        """
        self.app_dir = Path(app_dir).resolve()

    def load(self, reference: str | Path) -> AgentHook:
        """Load one ``AgentHook`` instance from a Python file.

        :param reference: Python file path containing a top-level ``AgentHook`` instance.
        :type reference: str | Path
        :return: Loaded ``AgentHook`` instance.
        :raises ValueError: If the file does not contain a discoverable ``AgentHook`` instance.
        """
        module_path = self._resolve_module_path(reference)
        module_name = self._module_name_from_path(module_path)
        attribute_name = self._discover_agent_hook_name(module_path)
        module = self._import_module(module_path, module_name)
        target = getattr(module, attribute_name)

        from agent_hooks.router import AgentHook

        if not isinstance(target, AgentHook):
            raise ValueError(
                f"Resolved '{attribute_name}' from '{module_path}' but it is not an AgentHook "
                "instance."
            )
        return target

    def _resolve_module_path(self, reference: str | Path) -> Path:
        """Resolve one Python file path against ``app_dir``.

        :param reference: Python file path, relative or absolute.
        :type reference: str | Path
        :return: Resolved absolute path.
        """
        module_path = Path(reference)
        if not module_path.is_absolute():
            module_path = self.app_dir / module_path
        return module_path.resolve()

    def _import_module(self, module_path: Path, module_name: str) -> ModuleType:
        """Load one Python file under a path-unique module name.

        The file is loaded by location rather than via ``import_module`` on the derived
        name so that the exact requested file is executed even when its module name
        collides with an already-imported module in a long-lived process (for example
        two ``app_dir`` values that each contain a ``hooks.py``). ``app_dir`` stays on
        ``sys.path`` during execution so the file's own absolute imports still resolve.

        :param module_path: Absolute path to the Python file to load.
        :type module_path: Path
        :param module_name: Derived dotted module name, used for a readable unique name.
        :type module_name: str
        :return: Imported Python module.
        :raises ValueError: If the file cannot be loaded.
        """
        importlib.invalidate_caches()
        digest = hashlib.sha1(str(module_path).encode("utf-8")).hexdigest()[:12]
        unique_name = f"agent_hooks_app_{module_name.replace('.', '_')}_{digest}"
        spec = importlib.util.spec_from_file_location(unique_name, module_path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Could not load Python file '{module_path}'.")

        module = importlib.util.module_from_spec(spec)
        with self._prepend_sys_path():
            sys.modules[unique_name] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                sys.modules.pop(unique_name, None)
                raise
        return module

    @contextlib.contextmanager
    def _prepend_sys_path(self) -> Iterator[None]:
        """Temporarily prepend ``app_dir`` to ``sys.path``."""
        path_string = str(self.app_dir)
        sys.path.insert(0, path_string)
        try:
            yield
        finally:
            if sys.path and sys.path[0] == path_string:
                sys.path.pop(0)
            else:
                with contextlib.suppress(ValueError):
                    sys.path.remove(path_string)

    def _module_name_from_path(self, module_path: Path) -> str:
        """Build an importable module name for a Python file inside ``app_dir``.

        :param module_path: Python file to map to an import string.
        :type module_path: Path
        :return: Importable module name.
        :raises ValueError: If the file is outside ``app_dir`` or cannot form a valid module name.
        """
        if module_path.suffix != ".py":
            raise ValueError(f"Expected a Python file, got '{module_path}'.")
        if not module_path.exists():
            raise ValueError(f"Python file '{module_path}' does not exist.")

        try:
            relative_module_path = module_path.relative_to(self.app_dir)
        except ValueError as exc:
            raise ValueError(
                f"Python file '{module_path}' must be inside app_dir '{self.app_dir}'."
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

    def _discover_agent_hook_name(self, module_path: Path) -> str:
        """Inspect a Python file and return the discovered ``AgentHook`` instance name.

        :param module_path: Python file to inspect.
        :type module_path: Path
        :return: Top-level variable name bound to an ``AgentHook`` instance.
        :raises ValueError: If no app instance is found or multiple ambiguous instances exist.
        """
        module = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
        constructor_names = self._collect_agent_hook_constructor_names(module)
        instance_names: list[str] = []
        for statement in module.body:
            instance_names.extend(
                self._find_agent_hook_assignment_names(statement, constructor_names)
            )

        unique_instance_names = tuple(dict.fromkeys(instance_names))
        if not unique_instance_names:
            raise ValueError(f"No top-level AgentHook() instance found in '{module_path}'.")
        if len(unique_instance_names) == 1:
            return unique_instance_names[0]
        if "app" in unique_instance_names:
            return "app"

        choices = ", ".join(unique_instance_names)
        raise ValueError(
            f"Multiple top-level AgentHook() instances found in '{module_path}': {choices}. "
            "Keep one instance, or name the desired one 'app'."
        )

    @staticmethod
    def _collect_agent_hook_constructor_names(module: ast.Module) -> set[str]:
        """Collect callable names that resolve to ``AgentHook`` in one module."""
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

    def _find_agent_hook_assignment_names(
        self,
        statement: ast.stmt,
        constructor_names: set[str],
    ) -> list[str]:
        """Return top-level variable names assigned from an ``AgentHook`` constructor."""
        if isinstance(statement, ast.Assign):
            value = statement.value
            targets = statement.targets
        elif isinstance(statement, ast.AnnAssign):
            value = statement.value
            targets = [statement.target]
        else:
            return []

        if value is None or not self._is_agent_hook_constructor_call(value, constructor_names):
            return []

        assignment_names: list[str] = []
        for target in targets:
            assignment_names.extend(self._extract_assignment_names(target))
        return assignment_names

    def _is_agent_hook_constructor_call(
        self,
        node: ast.AST,
        constructor_names: set[str],
    ) -> bool:
        """Return whether one AST node instantiates ``AgentHook``."""
        if not isinstance(node, ast.Call):
            return False
        dotted_name = self._render_dotted_name(node.func)
        return dotted_name in constructor_names

    def _render_dotted_name(self, node: ast.AST) -> str | None:
        """Render an AST name or attribute chain into dotted text."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base_name = self._render_dotted_name(node.value)
            if base_name is None:
                return None
            return f"{base_name}.{node.attr}"
        return None

    def _extract_assignment_names(self, node: ast.AST) -> list[str]:
        """Extract variable names from an assignment target."""
        if isinstance(node, ast.Name):
            return [node.id]
        if isinstance(node, ast.Tuple | ast.List):
            names: list[str] = []
            for element in node.elts:
                names.extend(self._extract_assignment_names(element))
            return names
        return []


def _emit_hook_response(
    response: HookResponseProtocol | None = None,
    *,
    provider: HookProvider | str | None = None,
    input_payload: HookPayload | None = None,
    stdout: IO[str] | None = None,
) -> None:
    """Emit the structured response JSON expected by the selected provider."""
    stream = stdout if stdout is not None else sys.stdout
    stream.write(_render_hook_response(response, provider=provider, input_payload=input_payload))


def _render_hook_response(
    response: HookResponseProtocol | None = None,
    *,
    provider: HookProvider | str | None = None,
    input_payload: HookPayload | None = None,
) -> str:
    """Render the structured response JSON expected by the selected provider."""
    buffer = StringIO()
    payload = provider_client.render_response_payload(
        response or HookResponse(),
        provider=provider,
        input_payload=input_payload,
    )
    json.dump(payload, buffer, separators=(",", ":"))
    buffer.write("\n")
    return buffer.getvalue()


def run_callback(
    hook: AgentHook,
    *,
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
    runtime_config: RuntimeConfig | None = None,
    transport: DisplayTransport | None = None,
    provider: HookProvider | str | None = None,
) -> int:
    """Process hook JSON from stdin with an ``AgentHook`` instance and emit the response.

    :param hook: ``AgentHook`` instance that owns callback dispatch.
    :type hook: AgentHook
    :param stdin: Optional stdin override.
    :type stdin: IO[str] | None
    :param stdout: Optional stdout override.
    :type stdout: IO[str] | None
    :param runtime_config: Optional runtime configuration override.
    :type runtime_config: RuntimeConfig | None
    :param transport: Optional UI transport override.
    :type transport: DisplayTransport | None
    :param provider: Optional hook protocol provider override.
    :type provider: HookProvider | str | None
    :return: Process exit code.
    """
    config = runtime_config or load_runtime_config()
    selected_provider = _resolve_provider(provider, hook, config)
    input_data = read_hook_input(stdin, provider=selected_provider)
    resolved_provider = input_data.payload.provider
    append_input_audit_log(
        InputAuditLogRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            provider=resolved_provider.value,
            hook_event_name=input_data.payload.raw_event_name,
            session_id=input_data.payload.session_id,
            cwd=input_data.payload.cwd,
            raw_input=input_data.raw_input,
        ),
        config.audit_logging.input_file,
    )
    display_transport = transport or NoopDisplayTransport()
    with use_runtime_config(config):
        result = hook.dispatch(input_data, display_transport)
    response_text = _render_hook_response(
        result.response,
        provider=resolved_provider,
        input_payload=input_data.payload,
    )

    timestamp = datetime.now(timezone.utc).isoformat()
    append_response_audit_log(
        ResponseAuditLogRecord(
            timestamp=timestamp,
            provider=resolved_provider.value,
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
            provider=resolved_provider.value,
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
    _emit_hook_response(
        result.response,
        provider=resolved_provider,
        input_payload=input_data.payload,
        stdout=stdout,
    )
    return 0


def _resolve_provider(
    provider: HookProvider | str | None,
    hook: AgentHook,
    runtime_config: RuntimeConfig,
) -> HookProvider | str | None:
    """Resolve the effective provider for one callback run."""
    if provider is not None:
        return provider_client.coerce_provider(provider)
    if hook.provider is not None:
        return provider_client.coerce_provider(hook.provider)
    return runtime_config.provider


__all__ = ["AgentHookFileLoader", "run_callback"]
