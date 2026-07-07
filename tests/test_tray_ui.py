from pathlib import Path
import types


class FakeSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self):
        for callback in self.callbacks:
            callback()


class FakeAction:
    def __init__(self, text):
        self.text = text
        self.triggered = FakeSignal()
        self.checkable = False
        self.checked = False
        self.enabled = True

    def setText(self, text):
        self.text = text

    def setCheckable(self, value):
        self.checkable = value

    def setChecked(self, value):
        self.checked = value

    def setEnabled(self, value):
        self.enabled = value

    def trigger(self):
        self.triggered.emit()


class FakeMenu:
    def __init__(self):
        self.items = []

    def addAction(self, text):
        action = FakeAction(text)
        self.items.append(action)
        return action

    def addSeparator(self):
        self.items.append("separator")


class FakeIcon:
    def __init__(self, path):
        self.path = path


class FakeSystemTrayIcon:
    Information = "information"
    instances = []

    def __init__(self, icon):
        self.icon = icon
        self.menu = None
        self.tooltip = ""
        self.visible = False
        self.messages = []
        FakeSystemTrayIcon.instances.append(self)

    def setContextMenu(self, menu):
        self.menu = menu

    def setToolTip(self, tooltip):
        self.tooltip = tooltip

    def setIcon(self, icon):
        self.icon = icon

    def show(self):
        self.visible = True

    def showMessage(self, title, message, icon=None, millisecondsTimeout=0):
        self.messages.append((title, message, icon, millisecondsTimeout))


class FakeTimer:
    callbacks = []

    @classmethod
    def singleShot(cls, interval, callback):
        cls.callbacks.append((interval, callback))

    @classmethod
    def flush(cls):
        queued = list(cls.callbacks)
        cls.callbacks.clear()
        for _interval, callback in queued:
            callback()


class FakeUrl:
    def __init__(self, path):
        self.path = path

    @classmethod
    def fromLocalFile(cls, path):
        return cls(path)


class FakeDesktopServices:
    opened = []

    @classmethod
    def openUrl(cls, url):
        cls.opened.append(url.path)
        return True


def fake_qt_modules():
    FakeSystemTrayIcon.instances = []
    FakeTimer.callbacks = []
    FakeDesktopServices.opened = []
    return types.SimpleNamespace(
        QtCore=types.SimpleNamespace(QTimer=FakeTimer, QUrl=FakeUrl),
        QtGui=types.SimpleNamespace(QIcon=FakeIcon, QDesktopServices=FakeDesktopServices),
        QtWidgets=types.SimpleNamespace(QSystemTrayIcon=FakeSystemTrayIcon, QMenu=FakeMenu),
    )


def action_by_text(menu, text):
    for item in menu.items:
        if getattr(item, "text", None) == text:
            return item
    raise AssertionError(f"missing menu action: {text}")


def test_default_tray_assets_are_real_ico_files():
    from voicetray.ui.tray import default_tray_assets

    assets = default_tray_assets()

    assert {path.name for path in assets.as_dict().values()} == {
        "mic_idle.ico",
        "mic_recording.ico",
        "mic_processing.ico",
    }
    for path in assets.as_dict().values():
        data = Path(path).read_bytes()
        assert data[:6] == b"\x00\x00\x01\x00\x01\x00"
        assert len(data) > 100


def test_default_asset_dir_uses_exe_sibling_assets_when_frozen(monkeypatch, tmp_path):
    import sys

    from voicetray.ui.tray import default_asset_dir

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "VoiceTray.exe"))

    assert default_asset_dir() == tmp_path / "assets" / "tray"


def test_tray_menu_queues_actions_and_updates_toggle_state(tmp_path):
    from voicetray.ui.tray import TrayCallbacks, TrayState, VoiceTrayTray

    events = []
    qt_modules = fake_qt_modules()
    tray = VoiceTrayTray(
        qt_modules=qt_modules,
        callbacks=TrayCallbacks(
            start_listening=lambda: events.append("start"),
            stop_listening=lambda: events.append("stop"),
            show_history=lambda: events.append("history"),
            show_settings=lambda: events.append("settings"),
            quit_app=lambda: events.append("quit"),
        ),
        model_label="small",
        log_dir=tmp_path,
    )

    tray_actions = [item.text for item in tray.menu.items if item != "separator"]
    assert tray_actions == [
        "Start Listening",
        "History...",
        "Settings...",
        "Open Log Folder",
        "Quit",
    ]
    assert tray.tray_icon.visible is True
    assert tray.tray_icon.tooltip == "VoiceTray - Idle - model small"

    action_by_text(tray.menu, "Start Listening").trigger()
    assert events == []
    FakeTimer.flush()
    assert events == ["start"]

    tray.set_listening(True)
    assert tray.toggle_action.text == "Stop Listening"
    assert tray.toggle_action.checked is True
    action_by_text(tray.menu, "Stop Listening").trigger()
    FakeTimer.flush()
    assert events[-1] == "stop"

    action_by_text(tray.menu, "History...").trigger()
    action_by_text(tray.menu, "Settings...").trigger()
    action_by_text(tray.menu, "Open Log Folder").trigger()
    action_by_text(tray.menu, "Quit").trigger()
    assert events == ["start", "stop"]
    FakeTimer.flush()
    assert events == ["start", "stop", "history", "settings", "quit"]
    assert FakeDesktopServices.opened == [str(tmp_path)]

    tray.set_state(TrayState.RECORDING)
    assert tray.tray_icon.icon.path.endswith("mic_recording.ico")
    assert tray.tray_icon.tooltip == "VoiceTray - Recording - model small"

    tray.set_state(TrayState.PROCESSING)
    assert tray.tray_icon.icon.path.endswith("mic_processing.ico")
    assert tray.tray_icon.tooltip == "VoiceTray - Processing - model small"

    tray.set_state(TrayState.NO_MICROPHONE)
    assert tray.tray_icon.icon.path.endswith("mic_idle.ico")
    assert tray.tray_icon.tooltip == "VoiceTray - No microphone - model small"

    tray.show_notification("Copied to history")
    assert tray.tray_icon.messages == [
        ("VoiceTray", "Copied to history", FakeSystemTrayIcon.Information, 4000)
    ]
