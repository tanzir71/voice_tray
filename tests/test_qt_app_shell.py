import ast
import sys
import types
from pathlib import Path


class FakeSignalDescriptor:
    def __init__(self, *args):
        self.args = args
        self.name = ""

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        channels = instance.__dict__.setdefault("_signal_channels", {})
        return channels.setdefault(self.name, FakeSignalChannel())


class FakeSignalChannel:
    def __init__(self):
        self.connected = []
        self.emitted = []

    def connect(self, callback):
        self.connected.append(callback)

    def emit(self, *args):
        self.emitted.append(args)
        for callback in self.connected:
            callback(*args)


class FakeQObject:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class FakeApplication:
    instance_value = None

    def __init__(self, argv):
        FakeApplication.instance_value = self
        self.argv = argv
        self.quit_on_last_window_closed = True
        self.application_name = None
        self.aboutToQuit = FakeSignalChannel()
        self.events = []

    @classmethod
    def instance(cls):
        return cls.instance_value

    def setApplicationName(self, name):
        self.application_name = name

    def setQuitOnLastWindowClosed(self, value):
        self.quit_on_last_window_closed = value

    def exec(self):
        self.events.append("exec")
        return 23


def fake_qt_modules():
    FakeApplication.instance_value = None
    return types.SimpleNamespace(
        QtCore=types.SimpleNamespace(QObject=FakeQObject, Signal=FakeSignalDescriptor),
        QtGui=types.SimpleNamespace(),
        QtWidgets=types.SimpleNamespace(QApplication=FakeApplication),
    )


def test_voice_tray_app_runs_qt_event_loop_and_controller():
    from voicetray.app import VoiceTrayApp

    events = []

    class FakeController:
        def __init__(self, signals):
            self.signals = signals

        def start(self):
            events.append("start")

        def stop(self):
            events.append("stop")

        def start_listening(self):
            events.append("start_listening")

        def stop_listening(self):
            events.append("stop_listening")

        def model_label(self):
            return "small"

    class FakeTray:
        def __init__(self, *, callbacks, model_label, **_kwargs):
            self.callbacks = callbacks
            self.model_label = model_label
            events.append(("tray", model_label))

        def set_listening(self, value):
            events.append(("listening", value))

        def set_state(self, state):
            events.append(("state", str(state)))

        def show_notification(self, message):
            events.append(("notification", message))

    class FakePill:
        def __init__(self, *, hotkey_hint, **_kwargs):
            events.append(("pill", hotkey_hint))

        def show_recording(self):
            events.append(("pill_state", "recording"))

        def update_level(self, level):
            events.append(("level", level))

        def show_processing(self):
            events.append(("pill_state", "processing"))

        def finish_success(self):
            events.append(("pill_state", "done"))

        def show_error(self, message):
            events.append(("pill_error", message))

    app = VoiceTrayApp(
        argv=["voicetray"],
        qt_modules=fake_qt_modules(),
        controller_factory=lambda signals: FakeController(signals),
        tray_factory=lambda **kwargs: FakeTray(**kwargs),
        pill_factory=lambda **kwargs: FakePill(**kwargs),
        config_loader=lambda **_kwargs: {"app": {"onboarded": True}},
        crash_guard_installer=lambda notify: None,
    )

    result = app.run()
    app.signals.recording_started.emit()
    app.signals.audio_level_changed.emit(0.5)
    app.signals.processing_started.emit()
    app.signals.processing_finished.emit("clean text")
    app.signals.error.emit("No microphone")
    app.signals.notification_requested.emit("Copied to history")
    app.tray.callbacks.start_listening()
    app.tray.callbacks.stop_listening()
    FakeApplication.instance_value.aboutToQuit.emit()

    assert result == 23
    assert events == [
        ("tray", "small"),
        ("pill", "F9"),
        "start",
        ("state", "TrayState.RECORDING"),
        ("pill_state", "recording"),
        ("level", 0.5),
        ("state", "TrayState.PROCESSING"),
        ("pill_state", "processing"),
        ("state", "TrayState.IDLE"),
        ("pill_state", "done"),
        ("state", "TrayState.NO_MICROPHONE"),
        ("pill_error", "No microphone"),
        ("notification", "Copied to history"),
        "start_listening",
        ("listening", True),
        "stop_listening",
        ("listening", False),
        "stop",
    ]
    assert FakeApplication.instance_value.application_name == "VoiceTray"
    assert FakeApplication.instance_value.quit_on_last_window_closed is False
    assert hasattr(app.signals, "notification_requested")
    assert hasattr(app.signals, "processing_finished")


def test_voice_tray_app_opens_in_process_settings_window():
    from voicetray.app import VoiceTrayApp

    events = []

    class FakeController:
        def __init__(self, _signals):
            pass

        def start(self):
            events.append("start")

        def stop(self):
            events.append("stop")

        def model_label(self):
            return "base"

        def hotkey_hint(self):
            return "F9"

        def apply_config(self, config):
            events.append(("applied", config["stt"]["model_size"]))

    class FakeTray:
        def __init__(self, *, callbacks, **_kwargs):
            self.callbacks = callbacks

        def set_listening(self, _value):
            pass

        def set_state(self, _state):
            pass

        def show_notification(self, message):
            events.append(("notification", message))

        def set_model_label(self, label):
            events.append(("model", label))

    class FakePill:
        def __init__(self, **_kwargs):
            pass

        def show_recording(self):
            pass

        def update_level(self, _level):
            pass

        def show_processing(self):
            pass

        def finish_success(self):
            pass

        def show_error(self, _message):
            pass

        def set_hotkey_hint(self, hint):
            events.append(("hotkey", hint))

    class FakeSettingsWindow:
        def __init__(self, *, on_config_applied, **_kwargs):
            self.on_config_applied = on_config_applied
            events.append("settings-created")

        def show_tab(self, tab_name):
            events.append(("tab", tab_name))

        def show(self):
            events.append("settings-show")

        def raise_(self):
            events.append("settings-raise")

        def activateWindow(self):
            events.append("settings-activate")

    app = VoiceTrayApp(
        argv=["voicetray"],
        qt_modules=fake_qt_modules(),
        controller_factory=lambda signals: FakeController(signals),
        tray_factory=lambda **kwargs: FakeTray(**kwargs),
        pill_factory=lambda **kwargs: FakePill(**kwargs),
        settings_window_factory=lambda **kwargs: FakeSettingsWindow(**kwargs),
        config_loader=lambda **_kwargs: {"app": {"onboarded": True}},
        crash_guard_installer=lambda notify: None,
    )

    assert app.run() == 23
    app.tray.callbacks.show_settings()
    app.settings_window.on_config_applied(
        {
            "stt": {"model_size": "small"},
            "hotkeys": {"speech": "f8"},
        }
    )

    assert events == [
        "start",
        ("model", "base"),
        "settings-created",
        "settings-show",
        "settings-raise",
        "settings-activate",
        ("applied", "small"),
        ("model", "base"),
        ("hotkey", "F8"),
    ]


def test_voice_tray_app_passes_model_download_callback_to_setup_windows():
    from voicetray.app import VoiceTrayApp

    events = []

    class FakeController:
        def __init__(self, _signals):
            pass

        def start(self):
            events.append("start")

        def stop(self):
            pass

        def model_label(self):
            return "base"

        def hotkey_hint(self):
            return "F9"

    class FakeTray:
        def __init__(self, *, callbacks, **_kwargs):
            self.callbacks = callbacks

        def set_listening(self, _value):
            pass

        def set_state(self, _state):
            pass

        def show_notification(self, _message):
            pass

        def set_model_label(self, _label):
            pass

    class FakePill:
        def __init__(self, **_kwargs):
            pass

        def show_recording(self):
            pass

        def update_level(self, _level):
            pass

        def show_processing(self):
            pass

        def finish_success(self):
            pass

        def show_error(self, _message):
            pass

    class FakeSettingsWindow:
        def __init__(self, *, model_download_callback, **_kwargs):
            events.append(("settings-callback", model_download_callback("small", lambda _value: None)))

        def show(self):
            pass

        def raise_(self):
            pass

        def activateWindow(self):
            pass

    class FakeOnboardingWindow:
        def __init__(self, *, model_download_callback, **_kwargs):
            events.append(("onboarding-callback", model_download_callback("base", lambda _value: None)))

        def update_audio_level(self, _level):
            pass

        def show(self):
            pass

        def raise_(self):
            pass

        def activateWindow(self):
            pass

    callback = lambda model, progress: f"download-{model}"
    app = VoiceTrayApp(
        argv=["voicetray"],
        qt_modules=fake_qt_modules(),
        controller_factory=lambda signals: FakeController(signals),
        tray_factory=lambda **kwargs: FakeTray(**kwargs),
        pill_factory=lambda **kwargs: FakePill(**kwargs),
        settings_window_factory=lambda **kwargs: FakeSettingsWindow(**kwargs),
        onboarding_window_factory=lambda **kwargs: FakeOnboardingWindow(**kwargs),
        config_loader=lambda **_kwargs: {"app": {"onboarded": False}},
        model_download_callback=callback,
        crash_guard_installer=lambda notify: None,
    )

    assert app.run() == 23
    app.tray.callbacks.show_settings()

    assert events == [
        "start",
        ("onboarding-callback", "download-base"),
        ("settings-callback", "download-small"),
    ]


def test_voice_tray_app_opens_in_process_history_window():
    from voicetray.app import VoiceTrayApp

    events = []

    class FakeController:
        def __init__(self, _signals):
            pass

        def start(self):
            events.append("start")

        def stop(self):
            events.append("stop")

        def model_label(self):
            return "base"

        def hotkey_hint(self):
            return "F9"

        def history_store(self):
            return "history-store"

        def reinsert_text(self, text):
            events.append(("reinsert", text))

    class FakeTray:
        def __init__(self, *, callbacks, **_kwargs):
            self.callbacks = callbacks

        def set_listening(self, _value):
            pass

        def set_state(self, _state):
            pass

        def show_notification(self, message):
            events.append(("notification", message))

        def set_model_label(self, _label):
            pass

    class FakePill:
        def __init__(self, **_kwargs):
            pass

        def show_recording(self):
            pass

        def update_level(self, _level):
            pass

        def show_processing(self):
            pass

        def finish_success(self):
            pass

        def show_error(self, _message):
            pass

    class FakeHistoryWindow:
        def __init__(self, *, store, reinsert_callback, **_kwargs):
            self.store = store
            self.reinsert_callback = reinsert_callback
            events.append(("history-created", store))

        def refresh(self):
            events.append("history-refresh")

        def show(self):
            events.append("history-show")

        def raise_(self):
            events.append("history-raise")

        def activateWindow(self):
            events.append("history-activate")

    app = VoiceTrayApp(
        argv=["voicetray"],
        qt_modules=fake_qt_modules(),
        controller_factory=lambda signals: FakeController(signals),
        tray_factory=lambda **kwargs: FakeTray(**kwargs),
        pill_factory=lambda **kwargs: FakePill(**kwargs),
        history_window_factory=lambda **kwargs: FakeHistoryWindow(**kwargs),
        config_loader=lambda **_kwargs: {"app": {"onboarded": True}},
        crash_guard_installer=lambda notify: None,
    )

    assert app.run() == 23
    app.tray.callbacks.show_history()
    app.history_window.reinsert_callback("hello again")

    assert events == [
        "start",
        ("history-created", "history-store"),
        "history-refresh",
        "history-show",
        "history-raise",
        "history-activate",
        ("reinsert", "hello again"),
    ]


def test_voice_tray_app_shows_onboarding_when_config_is_not_onboarded():
    from voicetray.app import VoiceTrayApp

    events = []

    class FakeController:
        def __init__(self, _signals):
            pass

        def start(self):
            events.append("start")

        def stop(self):
            events.append("stop")

        def model_label(self):
            return "base"

        def hotkey_hint(self):
            return "F9"

        def apply_config(self, config):
            events.append(("applied", config["app"]["onboarded"]))

    class FakeTray:
        def __init__(self, *, callbacks, **_kwargs):
            self.callbacks = callbacks

        def set_listening(self, _value):
            pass

        def set_state(self, _state):
            pass

        def show_notification(self, message):
            events.append(("notification", message))

        def set_model_label(self, label):
            events.append(("model", label))

    class FakePill:
        def __init__(self, **_kwargs):
            pass

        def show_recording(self):
            pass

        def update_level(self, _level):
            pass

        def show_processing(self):
            pass

        def finish_success(self):
            pass

        def show_error(self, _message):
            pass

        def set_hotkey_hint(self, hint):
            events.append(("hotkey", hint))

    class FakeOnboardingWindow:
        def __init__(self, *, on_config_applied, hotkey_hint, **_kwargs):
            self.on_config_applied = on_config_applied
            events.append(("onboarding-created", hotkey_hint))

        def update_audio_level(self, level):
            events.append(("onboarding-level", level))

        def show(self):
            events.append("onboarding-show")

        def raise_(self):
            events.append("onboarding-raise")

        def activateWindow(self):
            events.append("onboarding-activate")

    app = VoiceTrayApp(
        argv=["voicetray"],
        qt_modules=fake_qt_modules(),
        controller_factory=lambda signals: FakeController(signals),
        tray_factory=lambda **kwargs: FakeTray(**kwargs),
        pill_factory=lambda **kwargs: FakePill(**kwargs),
        onboarding_window_factory=lambda **kwargs: FakeOnboardingWindow(**kwargs),
        config_loader=lambda **_kwargs: {"app": {"onboarded": False}},
        crash_guard_installer=lambda notify: None,
    )

    assert app.run() == 23
    app.signals.audio_level_changed.emit(0.6)
    app.onboarding_window.on_config_applied(
        {"app": {"onboarded": True}, "stt": {"model_size": "small"}, "hotkeys": {"speech": "f8"}}
    )

    assert events == [
        "start",
        ("model", "base"),
        ("onboarding-created", "F9"),
        "onboarding-show",
        "onboarding-raise",
        "onboarding-activate",
        ("onboarding-level", 0.6),
        ("applied", True),
        ("model", "base"),
        ("hotkey", "F8"),
    ]


def test_voice_tray_app_installs_crash_guard_with_notification_signal():
    from voicetray.app import VoiceTrayApp

    events = []

    class FakeController:
        def __init__(self, _signals):
            pass

        def start(self):
            events.append("start")

        def stop(self):
            pass

        def model_label(self):
            return "base"

        def hotkey_hint(self):
            return "F9"

    class FakeTray:
        def __init__(self, *, callbacks, **_kwargs):
            self.callbacks = callbacks

        def set_listening(self, _value):
            pass

        def set_state(self, _state):
            pass

        def show_notification(self, message):
            events.append(("notification", message))

        def set_model_label(self, _label):
            pass

    class FakePill:
        def __init__(self, **_kwargs):
            pass

        def show_recording(self):
            pass

        def update_level(self, _level):
            pass

        def show_processing(self):
            pass

        def finish_success(self):
            pass

        def show_error(self, _message):
            pass

    def install_guard(notify):
        events.append("guard-installed")
        notify("VoiceTray hit an error — log saved")
        return "guard"

    app = VoiceTrayApp(
        argv=["voicetray"],
        qt_modules=fake_qt_modules(),
        controller_factory=lambda signals: FakeController(signals),
        tray_factory=lambda **kwargs: FakeTray(**kwargs),
        pill_factory=lambda **kwargs: FakePill(**kwargs),
        config_loader=lambda **_kwargs: {"app": {"onboarded": True}},
        crash_guard_installer=install_guard,
    )

    assert app.run() == 23

    assert app.crash_guard == "guard"
    assert events == [
        "guard-installed",
        ("notification", "VoiceTray hit an error — log saved"),
        "start",
    ]


def test_main_initializes_logging_config_and_qt_shell(monkeypatch):
    import voicetray.config as config
    import voicetray.logging_config as logging_config
    import voicetray.main as main

    calls = []

    class FakeQtApp:
        def run(self):
            calls.append("qt")
            return 0

    monkeypatch.setattr(logging_config, "configure_logging", lambda: calls.append("logging"))
    monkeypatch.setattr(config, "load_config", lambda: calls.append("config"))
    monkeypatch.setitem(
        sys.modules,
        "voicetray.app",
        types.SimpleNamespace(VoiceTrayApp=lambda: FakeQtApp()),
    )

    assert main.main() == 0
    assert calls == ["logging", "config", "qt"]


def test_runtime_sources_do_not_import_legacy_ui_stacks():
    root = Path(__file__).resolve().parents[1]
    forbidden = ("pystray", "tkinter", "from PIL", "ImageDraw")
    offenders = []
    for path in (root / "voicetray").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for term in forbidden:
            if term in text:
                offenders.append(f"{path.relative_to(root)}:{term}")

    assert offenders == []


def test_runtime_dependencies_use_pyside6_not_pystray_or_pillow():
    requirements = Path("requirements.txt").read_text(encoding="utf-8")

    assert "PySide6" in requirements
    assert "pystray" not in requirements
    assert "Pillow" not in requirements


def test_qt_app_shell_does_not_call_print():
    tree = ast.parse(Path("voicetray/app.py").read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    ]

    assert calls == []
