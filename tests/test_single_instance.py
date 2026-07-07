import json
import sys
import types


def test_single_instance_lock_blocks_second_acquire_and_releases(tmp_path):
    from voicetray.single_instance import SingleInstanceLock

    lock_path = tmp_path / "voicetray.lock"
    first = SingleInstanceLock(lock_path)
    second = SingleInstanceLock(lock_path)

    assert first.acquire() is True
    assert second.acquire() is False

    first.release()

    assert second.acquire() is True
    second.release()


def test_single_instance_lock_recovers_stale_lockfile(tmp_path):
    from voicetray.single_instance import SingleInstanceLock

    lock_path = tmp_path / "voicetray.lock"
    lock_path.write_text(json.dumps({"pid": 999999999, "created_at": 1}), encoding="utf-8")

    lock = SingleInstanceLock(lock_path)

    assert lock.acquire() is True
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    assert data["pid"] != 999999999
    lock.release()


def test_second_instance_notification_request_is_local_json(tmp_path):
    from voicetray.single_instance import (
        SingleInstanceLock,
        consume_existing_instance_notification,
    )

    lock = SingleInstanceLock(tmp_path / "voicetray.lock")
    notification_path = lock.notify_existing_instance("VoiceTray is already running")

    data = json.loads(notification_path.read_text(encoding="utf-8"))
    assert notification_path == tmp_path / "second-launch.json"
    assert data["message"] == "VoiceTray is already running"
    assert isinstance(data["pid"], int)
    assert isinstance(data["created_at"], float)

    consumed = consume_existing_instance_notification(tmp_path / "voicetray.lock")

    assert consumed["message"] == "VoiceTray is already running"
    assert not notification_path.exists()


def test_main_exits_before_qt_shell_when_lock_is_held(monkeypatch, tmp_path):
    import voicetray.config as config
    import voicetray.logging_config as logging_config
    import voicetray.main as main
    import voicetray.single_instance as single_instance

    calls = []
    lock_path = tmp_path / "voicetray.lock"
    held_lock = single_instance.SingleInstanceLock(lock_path)
    assert held_lock.acquire() is True

    monkeypatch.setattr(logging_config, "configure_logging", lambda: calls.append("logging"))
    monkeypatch.setattr(config, "load_config", lambda: calls.append("config"))
    monkeypatch.setattr(single_instance, "default_lock_path", lambda: lock_path)
    monkeypatch.setitem(
        sys.modules,
        "voicetray.app",
        types.SimpleNamespace(VoiceTrayApp=lambda: calls.append("qt")),
    )

    try:
        assert main.main() == 1
    finally:
        held_lock.release()

    assert calls == ["logging", "config"]
    notification = json.loads((tmp_path / "second-launch.json").read_text(encoding="utf-8"))
    assert notification["message"] == "VoiceTray is already running"
