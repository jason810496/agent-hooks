"""Load runtime configuration for agent hook processing."""

from __future__ import annotations

import logging
import math
import os
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from agent_hooks.enums import HookProvider

DEFAULT_LOG_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 5
DEFAULT_APPLICATION_LOG_LEVEL = "INFO"
DEFAULT_APPLICATION_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
DEFAULT_LOG_DIRECTORY_NAME = "logs"
DEFAULT_APPLICATION_LOG_FILENAME = "hooks.log"
DEFAULT_INPUT_AUDIT_LOG_FILENAME = "hooks.raw.log"
DEFAULT_RESPONSE_AUDIT_LOG_FILENAME = "hooks.response.log"
DEFAULT_DIALOG_FONT_SIZE = 13
DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_CHARS = 900
DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_LINES = 10
DEFAULT_COMMAND_PREVIEW_MAX_LINE_CHARS = 100
DEFAULT_NOTIFICATION_TIMEOUT_SECONDS = 10.0

APPLICATION_LOG_FORMAT_ENV_VAR = "AGENT_HOOK_APP_LOG_FORMAT"
APPLICATION_LOG_LEVEL_ENV_VAR = "AGENT_HOOK_APP_LOG_LEVEL"
APPLICATION_LOG_PATH_ENV_VAR = "AGENT_HOOK_APP_LOG_PATH"
APPLICATION_LOG_MAX_BYTES_ENV_VAR = "AGENT_HOOK_APP_LOG_MAX_BYTES"
APPLICATION_LOG_BACKUP_COUNT_ENV_VAR = "AGENT_HOOK_APP_LOG_BACKUP_COUNT"
COMMAND_PREVIEW_MAX_TOTAL_CHARS_ENV_VAR = "AGENT_HOOK_COMMAND_PREVIEW_MAX_TOTAL_CHARS"
COMMAND_PREVIEW_MAX_TOTAL_LINES_ENV_VAR = "AGENT_HOOK_COMMAND_PREVIEW_MAX_TOTAL_LINES"
COMMAND_PREVIEW_MAX_LINE_CHARS_ENV_VAR = "AGENT_HOOK_COMMAND_PREVIEW_MAX_LINE_CHARS"
DIALOG_FONT_SIZE_ENV_VAR = "AGENT_HOOK_DIALOG_FONT_SIZE"
NOTIFICATION_TIMEOUT_ENV_VAR = "AGENT_HOOK_NOTIFICATION_TIMEOUT"
PROVIDER_ENV_VAR = "AGENT_HOOK_PROVIDER"
DISABLE_OSASCRIPT_ENV_VARS = (
    "AGENT_HOOK_DISABLE_OSASCRIPT",
    "CLAUDE_HOOK_DISABLE_OSASCRIPT",
)
GLOBAL_LOG_BACKUP_COUNT_ENV_VAR = "AGENT_HOOK_LOG_BACKUP_COUNT"
GLOBAL_LOG_DIRECTORY_ENV_VAR = "AGENT_HOOK_LOG_DIR"
GLOBAL_LOG_MAX_BYTES_ENV_VAR = "AGENT_HOOK_LOG_MAX_BYTES"
INPUT_AUDIT_LOG_BACKUP_COUNT_ENV_VAR = "AGENT_HOOK_INPUT_AUDIT_LOG_BACKUP_COUNT"
INPUT_AUDIT_LOG_MAX_BYTES_ENV_VAR = "AGENT_HOOK_INPUT_AUDIT_LOG_MAX_BYTES"
INPUT_AUDIT_LOG_PATH_ENV_VAR = "AGENT_HOOK_INPUT_AUDIT_LOG_PATH"
PROJECT_ROOT_ENV_VAR = "AGENT_HOOK_PROJECT_ROOT"
RESPONSE_AUDIT_LOG_BACKUP_COUNT_ENV_VAR = "AGENT_HOOK_RESPONSE_AUDIT_LOG_BACKUP_COUNT"
RESPONSE_AUDIT_LOG_MAX_BYTES_ENV_VAR = "AGENT_HOOK_RESPONSE_AUDIT_LOG_MAX_BYTES"
RESPONSE_AUDIT_LOG_PATH_ENV_VAR = "AGENT_HOOK_RESPONSE_AUDIT_LOG_PATH"
TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_ENV_VALUES = frozenset({"0", "false", "no", "off"})
LOG_LEVEL_BY_NAME = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}


@dataclass(frozen=True)
class FileLoggingConfig:
    """Store rotation settings for one file-backed logger."""

    path: Path
    max_bytes: int
    backup_count: int


@dataclass(frozen=True)
class ApplicationLoggingConfig:
    """Store application logger configuration."""

    file: FileLoggingConfig
    level: int
    level_name: str
    format_string: str


@dataclass(frozen=True)
class AuditLoggingConfig:
    """Store audit logger configuration."""

    input_file: FileLoggingConfig
    response_file: FileLoggingConfig


@dataclass(frozen=True)
class RuntimeConfig:
    """Store filesystem and environment configuration for callback execution."""

    project_root: Path
    log_directory: Path
    provider: HookProvider | None
    skip_osascript: bool
    application_logging: ApplicationLoggingConfig
    audit_logging: AuditLoggingConfig
    dialog_font_size: int = DEFAULT_DIALOG_FONT_SIZE
    command_preview_max_total_chars: int = DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_CHARS
    command_preview_max_total_lines: int = DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_LINES
    command_preview_max_line_chars: int = DEFAULT_COMMAND_PREVIEW_MAX_LINE_CHARS
    notification_timeout_seconds: float = DEFAULT_NOTIFICATION_TIMEOUT_SECONDS
    warnings: tuple[str, ...] = ()

    @property
    def log_path(self) -> Path:
        """Return the application log path for compatibility.

        :return: Application log file path.
        """
        return self.application_logging.file.path

    @property
    def raw_log_path(self) -> Path:
        """Return the input audit log path for compatibility.

        :return: Input audit log file path.
        """
        return self.audit_logging.input_file.path

    @property
    def response_log_path(self) -> Path:
        """Return the response audit log path.

        :return: Response audit log file path.
        """
        return self.audit_logging.response_file.path


_ACTIVE_RUNTIME_CONFIG: ContextVar[RuntimeConfig | None] = ContextVar(
    "agent_hooks_active_runtime_config", default=None
)


def load_runtime_config(env: Mapping[str, str] | None = None) -> RuntimeConfig:
    """Build the runtime configuration from the current environment.

    :param env: Optional environment mapping override.
    :type env: Mapping[str, str] | None
    :return: Normalized runtime configuration.
    """
    if env is None:
        return _load_current_runtime_config()
    return _build_runtime_config(env)


@contextmanager
def use_runtime_config(config: RuntimeConfig) -> Iterator[None]:
    """Bind the active runtime configuration for the current execution context.

    Deep presentation helpers (for example command-preview formatting) read the
    bound configuration through :func:`get_active_runtime_config` so that an
    explicitly supplied :class:`RuntimeConfig` is honored instead of the cached
    process-environment configuration.

    :param config: Runtime configuration to bind for the nested block.
    :type config: RuntimeConfig
    """
    token = _ACTIVE_RUNTIME_CONFIG.set(config)
    try:
        yield
    finally:
        _ACTIVE_RUNTIME_CONFIG.reset(token)


def get_active_runtime_config() -> RuntimeConfig:
    """Return the runtime configuration bound for the current execution context.

    :return: The configuration bound by :func:`use_runtime_config`, or the cached
        process-environment configuration when none is bound.
    """
    active = _ACTIVE_RUNTIME_CONFIG.get()
    if active is not None:
        return active
    return load_runtime_config()


@cache
def _load_current_runtime_config() -> RuntimeConfig:
    """Build and cache runtime configuration from the process environment."""
    return _build_runtime_config(os.environ)


def _build_runtime_config(env: Mapping[str, str]) -> RuntimeConfig:
    """Build runtime configuration from an explicit environment mapping."""
    environment = env
    warnings: list[str] = []
    default_project_root = Path(__file__).resolve().parents[2]
    project_root = read_path_env(
        environment,
        PROJECT_ROOT_ENV_VAR,
        default=default_project_root,
        project_root=default_project_root,
    )
    log_directory = read_path_env(
        environment,
        GLOBAL_LOG_DIRECTORY_ENV_VAR,
        default=project_root / DEFAULT_LOG_DIRECTORY_NAME,
        project_root=project_root,
    )
    skip_osascript = read_boolean_env(
        environment,
        DISABLE_OSASCRIPT_ENV_VARS,
        default=False,
        warnings=warnings,
    )
    application_file = load_file_logging_config(
        env=environment,
        path_env_var=APPLICATION_LOG_PATH_ENV_VAR,
        max_bytes_env_var=APPLICATION_LOG_MAX_BYTES_ENV_VAR,
        backup_count_env_var=APPLICATION_LOG_BACKUP_COUNT_ENV_VAR,
        default_path=log_directory / DEFAULT_APPLICATION_LOG_FILENAME,
        project_root=project_root,
        warnings=warnings,
    )
    input_audit_file = load_file_logging_config(
        env=environment,
        path_env_var=INPUT_AUDIT_LOG_PATH_ENV_VAR,
        max_bytes_env_var=INPUT_AUDIT_LOG_MAX_BYTES_ENV_VAR,
        backup_count_env_var=INPUT_AUDIT_LOG_BACKUP_COUNT_ENV_VAR,
        default_path=log_directory / DEFAULT_INPUT_AUDIT_LOG_FILENAME,
        project_root=project_root,
        warnings=warnings,
    )
    response_audit_file = load_file_logging_config(
        env=environment,
        path_env_var=RESPONSE_AUDIT_LOG_PATH_ENV_VAR,
        max_bytes_env_var=RESPONSE_AUDIT_LOG_MAX_BYTES_ENV_VAR,
        backup_count_env_var=RESPONSE_AUDIT_LOG_BACKUP_COUNT_ENV_VAR,
        default_path=log_directory / DEFAULT_RESPONSE_AUDIT_LOG_FILENAME,
        project_root=project_root,
        warnings=warnings,
    )
    application_log_level, application_log_level_name = read_log_level_env(
        environment,
        APPLICATION_LOG_LEVEL_ENV_VAR,
        default=DEFAULT_APPLICATION_LOG_LEVEL,
        warnings=warnings,
    )
    application_log_format = read_text_env(
        environment,
        APPLICATION_LOG_FORMAT_ENV_VAR,
        default=DEFAULT_APPLICATION_LOG_FORMAT,
    )
    provider = read_provider_env(
        environment,
        PROVIDER_ENV_VAR,
        warnings=warnings,
    )
    dialog_font_size = read_positive_int_env(
        environment,
        DIALOG_FONT_SIZE_ENV_VAR,
        default=DEFAULT_DIALOG_FONT_SIZE,
        warnings=warnings,
    )
    command_preview_max_total_chars = read_positive_int_env(
        environment,
        COMMAND_PREVIEW_MAX_TOTAL_CHARS_ENV_VAR,
        default=DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_CHARS,
        warnings=warnings,
    )
    command_preview_max_total_lines = read_positive_int_env(
        environment,
        COMMAND_PREVIEW_MAX_TOTAL_LINES_ENV_VAR,
        default=DEFAULT_COMMAND_PREVIEW_MAX_TOTAL_LINES,
        warnings=warnings,
    )
    command_preview_max_line_chars = read_positive_int_env(
        environment,
        COMMAND_PREVIEW_MAX_LINE_CHARS_ENV_VAR,
        default=DEFAULT_COMMAND_PREVIEW_MAX_LINE_CHARS,
        warnings=warnings,
    )
    notification_timeout_seconds = read_timeout_env(
        environment,
        NOTIFICATION_TIMEOUT_ENV_VAR,
        default=DEFAULT_NOTIFICATION_TIMEOUT_SECONDS,
        warnings=warnings,
    )

    return RuntimeConfig(
        project_root=project_root,
        log_directory=log_directory,
        provider=provider,
        skip_osascript=skip_osascript,
        application_logging=ApplicationLoggingConfig(
            file=application_file,
            level=application_log_level,
            level_name=application_log_level_name,
            format_string=application_log_format,
        ),
        audit_logging=AuditLoggingConfig(
            input_file=input_audit_file,
            response_file=response_audit_file,
        ),
        dialog_font_size=dialog_font_size,
        command_preview_max_total_chars=command_preview_max_total_chars,
        command_preview_max_total_lines=command_preview_max_total_lines,
        command_preview_max_line_chars=command_preview_max_line_chars,
        notification_timeout_seconds=notification_timeout_seconds,
        warnings=tuple(warnings),
    )


load_runtime_config.cache_clear = _load_current_runtime_config.cache_clear  # type: ignore[attr-defined]


def read_provider_env(
    env: Mapping[str, str],
    env_var: str,
    *,
    warnings: list[str],
) -> HookProvider | None:
    """Parse the configured hook provider."""
    raw_value = env.get(env_var)
    if raw_value is None or raw_value == "":
        return None

    try:
        return HookProvider(raw_value)
    except ValueError:
        warnings.append(f"Ignored invalid provider {raw_value!r} from {env_var}.")
        return None


def load_file_logging_config(
    *,
    env: Mapping[str, str],
    path_env_var: str,
    max_bytes_env_var: str,
    backup_count_env_var: str,
    default_path: Path,
    project_root: Path,
    warnings: list[str],
) -> FileLoggingConfig:
    """Build the logging configuration for one rotating file.

    :param env: Environment mapping to read from.
    :type env: Mapping[str, str]
    :param path_env_var: Environment variable name for the log path.
    :type path_env_var: str
    :param max_bytes_env_var: Environment variable name for max bytes.
    :type max_bytes_env_var: str
    :param backup_count_env_var: Environment variable name for backup count.
    :type backup_count_env_var: str
    :param default_path: Default file path.
    :type default_path: Path
    :param project_root: Project root used for relative path resolution.
    :type project_root: Path
    :param warnings: Accumulator for config warnings.
    :type warnings: list[str]
    :return: File logging configuration.
    """
    path = read_path_env(env, path_env_var, default=default_path, project_root=project_root)
    max_bytes = read_non_negative_int_env(
        env,
        primary_env_var=max_bytes_env_var,
        fallback_env_vars=(GLOBAL_LOG_MAX_BYTES_ENV_VAR,),
        default=DEFAULT_LOG_MAX_BYTES,
        warnings=warnings,
    )
    backup_count = read_non_negative_int_env(
        env,
        primary_env_var=backup_count_env_var,
        fallback_env_vars=(GLOBAL_LOG_BACKUP_COUNT_ENV_VAR,),
        default=DEFAULT_LOG_BACKUP_COUNT,
        warnings=warnings,
    )
    return FileLoggingConfig(path=path, max_bytes=max_bytes, backup_count=backup_count)


def read_boolean_env(
    env: Mapping[str, str],
    env_vars: Sequence[str],
    *,
    default: bool,
    warnings: list[str],
) -> bool:
    """Parse a boolean environment value.

    :param env: Environment mapping to read from.
    :type env: Mapping[str, str]
    :param env_vars: Variable names to check in order.
    :type env_vars: Sequence[str]
    :param default: Default value when no valid override exists.
    :type default: bool
    :param warnings: Accumulator for config warnings.
    :type warnings: list[str]
    :return: Parsed boolean value.
    """
    for env_var in env_vars:
        raw_value = env.get(env_var)
        if raw_value is None:
            continue

        normalized = raw_value.strip().lower()
        if normalized in TRUE_ENV_VALUES:
            return True
        if normalized in FALSE_ENV_VALUES:
            return False

        warnings.append(
            f"Invalid boolean value for {env_var}: {raw_value!r}. Using default {default!r}."
        )
    return default


def read_log_level_env(
    env: Mapping[str, str],
    env_var: str,
    *,
    default: str,
    warnings: list[str],
) -> tuple[int, str]:
    """Parse an application log level from the environment.

    :param env: Environment mapping to read from.
    :type env: Mapping[str, str]
    :param env_var: Variable name to read.
    :type env_var: str
    :param default: Default log level name.
    :type default: str
    :param warnings: Accumulator for config warnings.
    :type warnings: list[str]
    :return: Numeric log level and canonical level name.
    """
    raw_value = env.get(env_var)
    if raw_value is None or not raw_value.strip():
        return normalize_log_level(default)

    try:
        normalized = raw_value.strip().upper()
        if normalized.isdigit():
            return normalize_log_level(int(normalized))
        return normalize_log_level(normalized)
    except ValueError:
        warnings.append(
            f"Invalid log level for {env_var}: {raw_value!r}. Using default {default!r}."
        )
        return normalize_log_level(default)


def read_non_negative_int_env(
    env: Mapping[str, str],
    *,
    primary_env_var: str,
    fallback_env_vars: Sequence[str],
    default: int,
    warnings: list[str],
) -> int:
    """Parse a non-negative integer from the environment.

    :param env: Environment mapping to read from.
    :type env: Mapping[str, str]
    :param primary_env_var: Primary variable name to read.
    :type primary_env_var: str
    :param fallback_env_vars: Fallback variable names checked in order.
    :type fallback_env_vars: Sequence[str]
    :param default: Default value when no valid override exists.
    :type default: int
    :param warnings: Accumulator for config warnings.
    :type warnings: list[str]
    :return: Parsed integer value.
    """
    for env_var in (primary_env_var, *fallback_env_vars):
        raw_value = env.get(env_var)
        if raw_value is None:
            continue

        try:
            value = int(raw_value)
        except ValueError:
            warnings.append(f"Invalid integer value for {env_var}: {raw_value!r}. Using fallback.")
            continue

        if value < 0:
            warnings.append(f"Negative integer value for {env_var}: {raw_value!r}. Using fallback.")
            continue

        return value

    return default


def read_positive_int_env(
    env: Mapping[str, str],
    env_var: str,
    *,
    default: int,
    warnings: list[str],
) -> int:
    """Parse an optional positive integer from the environment.

    :param env: Environment mapping to read from.
    :type env: Mapping[str, str]
    :param env_var: Variable name to read.
    :type env_var: str
    :param default: Default value when no valid override exists.
    :type default: int
    :param warnings: Accumulator for config warnings.
    :type warnings: list[str]
    :return: Parsed positive integer, or the default.
    """
    raw_value = env.get(env_var)
    if raw_value is None or not raw_value.strip():
        return default

    try:
        value = int(raw_value)
    except ValueError:
        warnings.append(f"Invalid integer value for {env_var}: {raw_value!r}. Using fallback.")
        return default

    if value <= 0:
        warnings.append(f"Non-positive integer value for {env_var}: {raw_value!r}. Using fallback.")
        return default

    return value


def read_timeout_env(
    env: Mapping[str, str],
    env_var: str,
    *,
    default: float,
    warnings: list[str],
) -> float:
    """Parse an optional non-negative timeout in seconds from the environment.

    A value of ``0`` disables the timeout so the AppleScript call waits
    indefinitely. Negative or non-numeric values fall back to the default.

    :param env: Environment mapping to read from.
    :type env: Mapping[str, str]
    :param env_var: Variable name to read.
    :type env_var: str
    :param default: Default value when no valid override exists.
    :type default: float
    :param warnings: Accumulator for config warnings.
    :type warnings: list[str]
    :return: Parsed timeout in seconds, or the default.
    """
    raw_value = env.get(env_var)
    if raw_value is None or not raw_value.strip():
        return default

    try:
        value = float(raw_value)
    except ValueError:
        warnings.append(f"Invalid number value for {env_var}: {raw_value!r}. Using fallback.")
        return default

    if not math.isfinite(value):
        warnings.append(f"Non-finite number value for {env_var}: {raw_value!r}. Using fallback.")
        return default

    if value < 0:
        warnings.append(f"Negative number value for {env_var}: {raw_value!r}. Using fallback.")
        return default

    return value


def read_path_env(
    env: Mapping[str, str],
    env_var: str,
    *,
    default: Path,
    project_root: Path,
) -> Path:
    """Read a filesystem path from the environment.

    :param env: Environment mapping to read from.
    :type env: Mapping[str, str]
    :param env_var: Variable name to read.
    :type env_var: str
    :param default: Default path when no override exists.
    :type default: Path
    :param project_root: Project root used for relative path resolution.
    :type project_root: Path
    :return: Normalized path value.
    """
    raw_value = env.get(env_var)
    if raw_value is None or not raw_value.strip():
        return default

    return normalize_path(raw_value, project_root=project_root)


def read_text_env(
    env: Mapping[str, str],
    env_var: str,
    *,
    default: str,
) -> str:
    """Read a text value from the environment.

    :param env: Environment mapping to read from.
    :type env: Mapping[str, str]
    :param env_var: Variable name to read.
    :type env_var: str
    :param default: Default value when no override exists.
    :type default: str
    :return: Text value from the environment, or the default.
    """
    raw_value = env.get(env_var)
    if raw_value is None or not raw_value.strip():
        return default
    return raw_value


def normalize_log_level(value: str | int) -> tuple[int, str]:
    """Normalize a log level name or integer.

    :param value: Raw log level value.
    :type value: str | int
    :return: Numeric log level and canonical level name.
    :raises ValueError: If the log level is invalid.
    """
    if isinstance(value, int):
        level_name = logging.getLevelName(value)
        if not isinstance(level_name, str) or level_name.startswith("Level "):
            msg = f"Unsupported numeric log level: {value!r}"
            raise ValueError(msg)
        return value, level_name

    level_name = value.strip().upper()
    level = LOG_LEVEL_BY_NAME.get(level_name)
    if level is None:
        msg = f"Unsupported log level: {value!r}"
        raise ValueError(msg)
    return level, level_name


def normalize_path(value: str, *, project_root: Path) -> Path:
    """Normalize a path, resolving relative values from the project root.

    :param value: Raw path string.
    :type value: str
    :param project_root: Project root used for relative paths.
    :type project_root: Path
    :return: Normalized path.
    """
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return project_root / path
