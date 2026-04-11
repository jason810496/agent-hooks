"""Load runtime configuration for agent hook processing."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5
DISABLE_OSASCRIPT_ENV_VARS = (
    "AGENT_HOOK_DISABLE_OSASCRIPT",
    "CLAUDE_HOOK_DISABLE_OSASCRIPT",
)


@dataclass(frozen=True)
class RuntimeConfig:
    """Store filesystem and environment configuration for callback execution."""

    project_root: Path
    log_path: Path
    raw_log_path: Path
    skip_osascript: bool


def load_runtime_config() -> RuntimeConfig:
    """Build the runtime configuration from the current environment.

    :return: Normalized runtime configuration.
    """
    project_root = Path(__file__).resolve().parents[2]
    skip_osascript = any(os.environ.get(name) == "1" for name in DISABLE_OSASCRIPT_ENV_VARS)
    return RuntimeConfig(
        project_root=project_root,
        log_path=project_root / "logs" / "hooks.log",
        raw_log_path=project_root / "logs" / "hooks.raw.log",
        skip_osascript=skip_osascript,
    )
