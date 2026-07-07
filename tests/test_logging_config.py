import ast
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def test_configure_logging_uses_localappdata_rotating_file(tmp_path):
    from voicetray.logging_config import configure_logging

    log_file = configure_logging(local_appdata=tmp_path, force=True)
    logger = logging.getLogger("voicetray")

    assert log_file == tmp_path / "VoiceTray" / "logs" / "voicetray.log"
    handlers = [handler for handler in logger.handlers if isinstance(handler, RotatingFileHandler)]
    assert len(handlers) == 1
    assert Path(handlers[0].baseFilename) == log_file
    assert handlers[0].maxBytes == 1_000_000
    assert handlers[0].backupCount == 5


def test_configure_logging_honors_verbose_env_level(tmp_path, monkeypatch):
    from voicetray.logging_config import configure_logging

    monkeypatch.setenv("VOICETRAY_LOG_LEVEL", "DEBUG")

    configure_logging(local_appdata=tmp_path, force=True)

    assert logging.getLogger("voicetray").level == logging.DEBUG


def test_configure_logging_can_emit_to_console_for_debug_runs(tmp_path, monkeypatch):
    from voicetray.logging_config import configure_logging

    monkeypatch.setenv("VOICETRAY_LOG_CONSOLE", "1")

    configure_logging(local_appdata=tmp_path, force=True)

    handlers = logging.getLogger("voicetray").handlers
    assert any(
        isinstance(handler, logging.StreamHandler)
        and getattr(handler, "stream", None) is sys.stderr
        and getattr(handler, "_voicetray_console_handler", False)
        for handler in handlers
    )


def test_voicetray_production_sources_do_not_call_print():
    roots = [Path("voicetray"), Path("dictation")]
    offenders = []

    for root in roots:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "print"
                ):
                    offenders.append(f"{path}:{node.lineno}")

    assert offenders == []
