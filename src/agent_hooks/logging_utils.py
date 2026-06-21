"""Write structured callback logs."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler

from agent_hooks.config import ApplicationLoggingConfig, FileLoggingConfig
from agent_hooks.models.schemas.log_records import (
    ApplicationLogRecord,
    InputAuditLogRecord,
    ResponseAuditLogRecord,
)
from agent_hooks.serialization import serialize_json_value

APPLICATION_LOGGER_NAME = "agent-hooks.application"
INPUT_AUDIT_LOGGER_NAME = "agent-hooks.audit.input"
RESPONSE_AUDIT_LOGGER_NAME = "agent-hooks.audit.response"


def append_application_log(entry: ApplicationLogRecord, config: ApplicationLoggingConfig) -> None:
    """Write one application log record.

    :param entry: Application log record to append.
    :type entry: ApplicationLogRecord
    :param config: Application logging configuration.
    :type config: ApplicationLoggingConfig
    """
    try:
        logger = build_file_logger(
            APPLICATION_LOGGER_NAME,
            config.file,
            level=config.level,
            formatter=logging.Formatter(config.format_string),
        )
        line = json.dumps(serialize_json_value(entry), ensure_ascii=True, sort_keys=True)
        log_level = logging.ERROR if entry.error else logging.INFO
        logger.log(log_level, line)
    except (OSError, TypeError, ValueError):
        return


def append_input_audit_log(entry: InputAuditLogRecord, file_config: FileLoggingConfig) -> None:
    """Append the raw hook stdin payload to the input audit log.

    :param entry: Input audit log record to append.
    :type entry: InputAuditLogRecord
    :param file_config: File logging configuration.
    :type file_config: FileLoggingConfig
    """
    try:
        logger = build_file_logger(
            INPUT_AUDIT_LOGGER_NAME,
            file_config,
            level=logging.INFO,
            formatter=logging.Formatter("%(message)s"),
        )
        logger.info(json.dumps(serialize_json_value(entry), ensure_ascii=True, sort_keys=True))
    except (OSError, TypeError):
        return


def append_response_audit_log(
    entry: ResponseAuditLogRecord,
    file_config: FileLoggingConfig,
) -> None:
    """Append the emitted hook response to the response audit log.

    :param entry: Response audit log record to append.
    :type entry: ResponseAuditLogRecord
    :param file_config: File logging configuration.
    :type file_config: FileLoggingConfig
    """
    try:
        logger = build_file_logger(
            RESPONSE_AUDIT_LOGGER_NAME,
            file_config,
            level=logging.INFO,
            formatter=logging.Formatter("%(message)s"),
        )
        logger.info(json.dumps(serialize_json_value(entry), ensure_ascii=True, sort_keys=True))
    except (OSError, TypeError):
        return


def build_file_logger(
    name: str,
    file_config: FileLoggingConfig,
    *,
    level: int,
    formatter: logging.Formatter,
) -> logging.Logger:
    """Build a rotating file logger for one file.

    :param name: Logger name.
    :type name: str
    :param file_config: File logging configuration.
    :type file_config: FileLoggingConfig
    :param level: Logger level.
    :type level: int
    :param formatter: Formatter applied to the file handler.
    :type formatter: logging.Formatter
    :return: Configured logger instance.
    """
    file_config.path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    reset_logger_handlers(logger)
    handler = RotatingFileHandler(
        file_config.path,
        maxBytes=file_config.max_bytes,
        backupCount=file_config.backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def reset_logger_handlers(logger: logging.Logger) -> None:
    """Close and remove all handlers attached to a logger.

    :param logger: Logger to reset.
    :type logger: logging.Logger
    """
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
