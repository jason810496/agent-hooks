"""Write structured callback logs."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from agent_hooks.config import LOG_BACKUP_COUNT, LOG_MAX_BYTES
from agent_hooks.models import HookLogRecord, HookPayload
from agent_hooks.serialization import serialize_json_value


def append_log(entry: HookLogRecord) -> None:
    """Write one structured JSON log record.

    :param entry: Log record to append.
    :type entry: HookLogRecord
    """
    try:
        logger = make_file_logger("agent-hooks", entry.log_path)
        logger.info(json.dumps(serialize_json_value(entry), ensure_ascii=True, sort_keys=True))
    except (OSError, TypeError):
        return


def append_raw_input_log(
    *, timestamp: str, payload: HookPayload, raw_input: str, path: Path
) -> None:
    """Append the raw hook stdin payload to a human-readable log.

    :param timestamp: UTC timestamp for the record.
    :type timestamp: str
    :param payload: Normalized hook payload.
    :type payload: HookPayload
    :param raw_input: Exact stdin content.
    :type raw_input: str
    :param path: Raw log file path.
    :type path: Path
    """
    try:
        hook_event_name = payload.raw_event_name or "unknown"
        session_id = payload.session_id or "unknown"

        header = (
            f"--- timestamp={timestamp} hook_event_name={hook_event_name} session_id={session_id}"
        )
        if payload.cwd:
            header += f" cwd={payload.cwd}"
        header += " ---"

        logger = make_file_logger("agent-hooks.raw", path)
        if raw_input:
            logger.info("%s\n%s", header, raw_input.rstrip("\n"))
        else:
            logger.info(header)
    except OSError:
        return


def make_file_logger(
    name: str,
    path: Path,
    *,
    max_bytes: int = LOG_MAX_BYTES,
    backup_count: int = LOG_BACKUP_COUNT,
) -> logging.Logger:
    """Build or reuse a rotating file logger.

    :param name: Logger name.
    :type name: str
    :param path: Log file path.
    :type path: Path
    :param max_bytes: Maximum file size before rotation.
    :type max_bytes: int
    :param backup_count: Number of rotated files to keep.
    :type backup_count: int
    :return: Configured logger instance.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = RotatingFileHandler(
            path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger
