import types

import numpy as np


class FakeRecorder:
    def __init__(self):
        self.started = 0
        self.stopped = 0
        self.audio = np.array([0.1, 0.2], dtype=np.float32)

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1
        return self.audio


class ImmediateThread:
    def __init__(self, target, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        self.target(*self.args)


class FakeTimer:
    def __init__(self, interval, callback):
        self.interval = interval
        self.callback = callback
        self.started = False
        self.canceled = False

    def start(self):
        self.started = True

    def cancel(self):
        self.canceled = True

    def fire(self):
        self.callback()


class FakeTimerFactory:
    def __init__(self):
        self.timers = []

    def __call__(self, interval, callback):
        timer = FakeTimer(interval, callback)
        self.timers.append(timer)
        return timer


def make_app():
    from voicetray.legacy_app import VoiceTrayApp

    app = VoiceTrayApp.__new__(VoiceTrayApp)
    app.is_recording = False
    app.is_listening = False
    app.icon = None
    app.hotkey = "f9"
    app.alternate_hotkey = "ctrl+win"
    app.save_hotkey = "f10"
    app.cancel_hotkey = "esc"
    app.tap_lock_ms = 300
    app.recording_max_seconds = 600
    app.recording_warning_seconds = 540
    app.recording_warning_timer = None
    app.recording_cap_timer = None
    app.timer_factory = FakeTimerFactory()
    app.save_hotkey_handle = None
    return app


def test_legacy_hold_recording_stops_recorder_and_processes_captured_audio(monkeypatch):
    import voicetray.legacy_app as legacy_app

    app = make_app()
    recorder = FakeRecorder()
    app.audio_recorder = recorder
    app.get_active_window_identity = lambda: "start-hwnd"
    app.stt_engine = types.SimpleNamespace(transcribe=lambda audio: "raw transcript")
    processed = []
    app.process_raw_transcript = lambda raw, *, insert_text, duration_seconds=None, timings=None: processed.append(
        (raw, insert_text, duration_seconds, timings)
    )
    monkeypatch.setattr(legacy_app.threading, "Thread", ImmediateThread)

    app.start_hotkey_recording()
    app.finish_hotkey_recording(types.SimpleNamespace(duration_seconds=0.8, locked=False))

    assert recorder.started == 1
    assert recorder.stopped == 1
    assert processed == [("raw transcript", True, 0.8, {"record": 0.8})]
    assert app.is_recording is False
    assert app.recording_focus_token is None
    assert all(timer.canceled for timer in app.timer_factory.timers)


def test_legacy_recording_emits_ui_state_callbacks(monkeypatch):
    import voicetray.legacy_app as legacy_app

    app = make_app()
    recorder = FakeRecorder()
    app.audio_recorder = recorder
    app.get_active_window_identity = lambda: "start-hwnd"
    app.stt_engine = types.SimpleNamespace(transcribe=lambda audio: "raw transcript")
    app.process_raw_transcript = lambda raw, *, insert_text, duration_seconds=None, timings=None: "clean text"
    events = []
    app.recording_started_callback = lambda: events.append("recording_started")
    app.recording_stopped_callback = lambda duration: events.append(("recording_stopped", duration))
    app.processing_started_callback = lambda: events.append("processing_started")
    app.processing_finished_callback = lambda text: events.append(("processing_finished", text))
    monkeypatch.setattr(legacy_app.threading, "Thread", ImmediateThread)

    app.start_hotkey_recording()
    app.finish_hotkey_recording(types.SimpleNamespace(duration_seconds=1.5, locked=False))

    assert events == [
        "recording_started",
        ("recording_stopped", 1.5),
        "processing_started",
        ("processing_finished", "clean text"),
    ]


def test_legacy_recording_schedules_nine_minute_warning_and_ten_minute_cap():
    app = make_app()
    app.audio_recorder = FakeRecorder()
    app.get_active_window_identity = lambda: "start-hwnd"

    app.start_hotkey_recording()

    assert [timer.interval for timer in app.timer_factory.timers] == [540, 600]
    assert all(timer.started for timer in app.timer_factory.timers)


def test_legacy_recording_warning_timer_notifies_user():
    app = make_app()
    app.audio_recorder = FakeRecorder()
    app.get_active_window_identity = lambda: "start-hwnd"
    notifications = []
    app.show_tray_notification = notifications.append

    app.start_hotkey_recording()
    app.timer_factory.timers[0].fire()

    assert notifications == ["Recording will stop at 10:00. Finish up soon."]


def test_legacy_recording_cap_forces_stop_through_hotkey_controller(monkeypatch):
    import voicetray.legacy_app as legacy_app

    app = make_app()
    app.audio_recorder = FakeRecorder()
    app.get_active_window_identity = lambda: "start-hwnd"
    app.stt_engine = types.SimpleNamespace(transcribe=lambda audio: "raw transcript")
    app.process_raw_transcript = lambda raw, *, insert_text, duration_seconds=None, timings=None: processed.append(
        (raw, insert_text, duration_seconds, timings)
    ) or raw
    notifications = []
    processed = []
    app.show_tray_notification = notifications.append
    monkeypatch.setattr(legacy_app.threading, "Thread", ImmediateThread)

    class FakeController:
        def force_stop(self):
            return app.finish_hotkey_recording(types.SimpleNamespace(duration_seconds=600, locked=True))

    app.hotkey_controller = FakeController()

    app.start_hotkey_recording()
    app.timer_factory.timers[1].fire()

    assert notifications == ["Recording stopped at the 10-minute limit."]
    assert app.audio_recorder.stopped == 1
    assert app.is_recording is False
    assert processed == [("raw transcript", True, 600, {"record": 600})]


def test_legacy_audio_recorder_uses_configured_ten_minute_cap():
    from voicetray.stt.whisper_engine import WhisperEngineConfig

    app = make_app()
    app.recording_max_seconds = 600
    app.stt_config = WhisperEngineConfig()
    app.on_stt_state = lambda _state: None

    app.init_speech_engine()

    assert app.audio_recorder.max_seconds == 600.0


def test_legacy_start_listening_uses_hold_controller_for_speech_hotkey(monkeypatch):
    import voicetray.legacy_app as legacy_app

    app = make_app()
    controller_calls = []
    app.hotkey_controller = types.SimpleNamespace(
        start=lambda keyboard_module: controller_calls.append(("start", keyboard_module)),
        stop=lambda: controller_calls.append(("stop", None)),
    )

    added = []
    removed = []
    monkeypatch.setattr(
        legacy_app.keyboard,
        "add_hotkey",
        lambda hotkey, callback: added.append((hotkey, callback)) or "save-handle",
    )
    monkeypatch.setattr(legacy_app.keyboard, "remove_hotkey", lambda handle: removed.append(handle))

    app.start_listening()

    assert controller_calls == [("start", legacy_app.keyboard)]
    assert [hotkey for hotkey, _callback in added] == ["f10"]

    app.stop_listening()

    assert controller_calls == [("start", legacy_app.keyboard), ("stop", None)]
    assert removed == ["save-handle"]


def test_legacy_save_hotkey_records_to_history_without_text_file_append():
    app = make_app()
    app.is_recording = True
    notifications = []
    app.speech_to_text_for_saving = lambda: "clean note"
    app.show_minimal_save_feedback = notifications.append

    app.record_and_save_to_history()

    assert notifications == ["clean note"]
    assert app.is_recording is False
    assert not hasattr(app, "save_text_to_file")


def test_legacy_start_recording_reports_no_microphone_gracefully():
    from voicetray.audio.recorder import NoInputDeviceError

    app = make_app()
    errors = []
    app.error_callback = errors.append
    app.recording_started_callback = lambda: errors.append("started")
    app.get_active_window_identity = lambda: "start-hwnd"

    class MissingRecorder:
        def start(self):
            raise NoInputDeviceError("No microphone")

    app.audio_recorder = MissingRecorder()

    app.start_hotkey_recording()

    assert errors == ["No microphone"]
    assert app.is_recording is False


def test_legacy_hotkey_watchdog_restarts_dead_listener_and_save_hotkey(monkeypatch):
    import voicetray.legacy_app as legacy_app

    app = make_app()
    app.is_listening = True
    app.save_hotkey_handle = "old-save"
    notifications = []
    app.show_tray_notification = notifications.append

    class FakeController:
        def __init__(self):
            self.calls = 0

        def restart_if_dead(self):
            self.calls += 1
            return True

    controller = FakeController()
    app.hotkey_controller = controller
    removed = []
    added = []
    monkeypatch.setattr(legacy_app.keyboard, "remove_hotkey", lambda handle: removed.append(handle))
    monkeypatch.setattr(
        legacy_app.keyboard,
        "add_hotkey",
        lambda hotkey, callback: added.append((hotkey, callback)) or "new-save",
    )

    assert app.restart_dead_hotkey_listener() is True

    assert controller.calls == 1
    assert removed == ["old-save"]
    assert added == [("f10", app.on_save_hotkey_press)]
    assert app.save_hotkey_handle == "new-save"
    assert notifications == ["VoiceTray restarted hotkeys after a listener error."]
