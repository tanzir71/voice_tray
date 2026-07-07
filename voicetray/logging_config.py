"""Application logging setup."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE_NAME = "voicetray.log"
MAX_LOG_BYTES = 1_000_000
BACKUP_COUNT = 5


def _default_local_appdata() -> Path:
    configured = os.environ.get("LOCALAPPDATA")
    if configured:
        return Path(configured)
    return Path.home() / "AppData" / "Local"


def log_file_path(local_appdata: str | os.PathLike[str] | None = None) -> Path:
    base = Path(local_appdata) if local_appdata is not None else _default_local_appdata()
    return base / "VoiceTray" / "logs" / LOG_FILE_NAME


def configure_logging(
    *,
    level: int | None = None,
    local_appdata: str | os.PathLike[str] | None = None,
    force: bool = False,
) -> Path:
    """Configure package logging to a rotating file under LOCALAPPDATA."""

    log_file = log_file_path(local_appdata)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    resolved_level = _resolve_log_level(level)

    logger = logging.getLogger("voicetray")
    logger.setLevel(resolved_level)
    logger.propagate = False

    if force:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
    else:
        has_file_handler = any(
            getattr(handler, "_voicetray_file_handler", False)
            for handler in logger.handlers
        )
        has_console_handler = any(
            getattr(handler, "_voicetray_console_handler", False)
            for handler in logger.handlers
        )
        if has_file_handler:
            if _console_logging_enabled() and not has_console_handler:
                _add_console_handler(logger, resolved_level)
                return log_file
            if not _console_logging_enabled() or has_console_handler:
                return log_file

    handler = RotatingFileHandler(
        log_file,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler._voicetray_file_handler = True
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    logger.addHandler(handler)

    if _console_logging_enabled():
        _add_console_handler(logger, resolved_level)

    return log_file


def _resolve_log_level(level: int | None) -> int:
    if level is not None:
        return level
    name = os.environ.get("VOICETRAY_LOG_LEVEL", "INFO").strip().upper()
    resolved = getattr(logging, name, logging.INFO)
    return resolved if isinstance(resolved, int) else logging.INFO


def _console_logging_enabled() -> bool:
    return os.environ.get("VOICETRAY_LOG_CONSOLE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _add_console_handler(logger: logging.Logger, level: int) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler._voicetray_console_handler = True
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
    logger.addHandler(handler)
