from pathlib import Path


def _script_text(name: str) -> str:
    return Path(name).read_text(encoding="utf-8").lower()


def test_run_app_uses_pythonw_module_entrypoint_without_console_pause():
    script = _script_text("run_app.bat")

    assert "pythonw -m voicetray" in script
    assert "speech_to_text_app.py" not in script
    assert " pause" not in script
    assert "start" not in script


def test_run_debug_uses_console_python_with_verbose_logging():
    script = _script_text("run_debug.bat")

    assert "set voicetray_log_level=debug" in script
    assert "set voicetray_log_console=1" in script
    assert "python -m voicetray" in script
    assert "pythonw" not in script
    assert "pause" in script
