import logging
import sys
import types


def test_crash_guard_logs_traceback_notifies_and_returns(caplog):
    from voicetray.crash_guard import CrashGuard

    notifications = []
    guard = CrashGuard(notify=notifications.append)

    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        with caplog.at_level(logging.ERROR, logger="voicetray.crash_guard"):
            guard.handle_exception(type(exc), exc, exc.__traceback__)

    assert notifications == ["VoiceTray hit an error — log saved"]
    assert "Unhandled VoiceTray exception" in caplog.text
    assert "RuntimeError: boom" in caplog.text


def test_crash_guard_threading_hook_uses_exception_args(caplog):
    from voicetray.crash_guard import CrashGuard

    notifications = []
    guard = CrashGuard(notify=notifications.append)

    try:
        raise ValueError("thread boom")
    except ValueError as exc:
        args = types.SimpleNamespace(
            exc_type=type(exc),
            exc_value=exc,
            exc_traceback=exc.__traceback__,
            thread=types.SimpleNamespace(name="worker"),
        )
        with caplog.at_level(logging.ERROR, logger="voicetray.crash_guard"):
            guard.threading_excepthook(args)

    assert notifications == ["VoiceTray hit an error — log saved"]
    assert "worker" in caplog.text
    assert "ValueError: thread boom" in caplog.text


def test_install_crash_guard_installs_sys_and_thread_hooks(monkeypatch):
    import threading

    from voicetray.crash_guard import install_crash_guard

    monkeypatch.setattr(sys, "excepthook", lambda *_args: None)
    monkeypatch.setattr(threading, "excepthook", lambda _args: None)

    guard = install_crash_guard(notify=lambda _message: None)

    assert sys.excepthook == guard.excepthook
    assert threading.excepthook == guard.threading_excepthook
