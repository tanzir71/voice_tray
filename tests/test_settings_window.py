import json
import os
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def qt_modules():
    from PySide6 import QtCore, QtGui, QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return types.SimpleNamespace(QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets)


class FakeAutoStartManager:
    def __init__(self):
        self.enabled = False
        self.calls = []

    def is_enabled(self):
        return self.enabled

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        self.calls.append(bool(enabled))


def write_config(tmp_path, overrides=None):
    from voicetray.config import default_config, save_config

    cfg = default_config()
    cfg["dictation"]["glossary_path"] = str(tmp_path / "glossary.json")
    cfg["dictation"]["app_profiles_path"] = str(tmp_path / "app_profiles.json")
    cfg["dictation"]["profile"] = "notes"
    cfg["stt"]["language"] = "auto"
    if overrides:
        for section, values in overrides.items():
            cfg[section].update(values)
    path = tmp_path / "config.json"
    save_config(cfg, path)
    (tmp_path / "glossary.json").write_text(
        json.dumps({"user_terms": ["VoiceTray"], "protected_terms": [], "replacements": {}}),
        encoding="utf-8",
    )
    (tmp_path / "snippets.txt").write_text("addr=123 Main\n", encoding="utf-8")
    (tmp_path / "app_profiles.json").write_text("[]\n", encoding="utf-8")
    return path


def make_window(tmp_path, *, overrides=None, on_config_applied=None):
    from voicetray.ui.settings_window import SettingsWindow

    config_path = write_config(tmp_path, overrides)
    autostart = FakeAutoStartManager()
    window = SettingsWindow(
        qt_modules=qt_modules(),
        config_path=config_path,
        snippets_path=tmp_path / "snippets.txt",
        autostart_manager=autostart,
        on_config_applied=on_config_applied,
    )
    return window, config_path, autostart


def test_settings_window_has_required_tabs_and_loads_values(tmp_path):
    window, _config_path, _autostart = make_window(tmp_path)

    tabs = [window.tabs.tabText(index) for index in range(window.tabs.count())]

    assert tabs == ["General", "Cleanup", "Dictionary", "Snippets", "Models", "About"]
    assert window.speech_hotkey_edit.text() == "f9"
    assert window.language_combo.currentText() == "auto"
    assert window.mode_combo.currentText() == "balanced"
    assert window.profile_combo.currentText() == "notes"
    assert window.model_combo.currentText() == "base"
    assert "VoiceTray" in window.dictionary_editor.toPlainText()
    assert "addr=123 Main" in window.snippets_editor.toPlainText()


def test_settings_window_applies_config_live_and_updates_autostart(tmp_path):
    applied = []
    window, config_path, autostart = make_window(tmp_path, on_config_applied=applied.append)

    window.speech_hotkey_edit.setText("ctrl+shift+r")
    window.save_hotkey_edit.setText("f8")
    window.autostart_checkbox.setChecked(True)
    window.language_combo.setCurrentText("en")
    window.mode_combo.setCurrentText("aggressive")
    window.profile_combo.setCurrentText("email")
    window.model_combo.setCurrentText("small")
    window.llm_enabled_checkbox.setChecked(True)
    window.llm_path_edit.setText("models/qwen.gguf")

    assert window.apply_changes() is True

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["hotkeys"]["speech"] == "ctrl+shift+r"
    assert saved["hotkeys"]["save"] == "f8"
    assert saved["app"]["start_with_windows"] is True
    assert saved["stt"]["language"] == "en"
    assert saved["dictation"]["mode"] == "aggressive"
    assert saved["dictation"]["profile"] == "email"
    assert saved["stt"]["model_size"] == "small"
    assert saved["llm"]["enabled"] is True
    assert saved["llm"]["model_path"] == "models/qwen.gguf"
    assert autostart.calls == [True]
    assert applied[-1] == saved


def test_settings_window_blocks_duplicate_hotkeys(tmp_path):
    window, config_path, _autostart = make_window(tmp_path)
    before = json.loads(config_path.read_text(encoding="utf-8"))

    window.speech_hotkey_edit.setText("f8")
    window.save_hotkey_edit.setText("f8")

    assert window.apply_changes() is False
    assert "conflict" in window.status_label.text().lower()
    assert json.loads(config_path.read_text(encoding="utf-8")) == before


def test_settings_window_saves_dictionary_snippets_and_profiles(tmp_path):
    window, _config_path, _autostart = make_window(tmp_path)
    dictionary = {
        "user_terms": ["Qwen Turbo"],
        "protected_terms": ["ACME-123"],
        "replacements": {"voice tray": "VoiceTray"},
    }
    profiles = [{"match": "Code", "profile": "code/comments", "mode": "raw"}]

    window.dictionary_editor.setPlainText(json.dumps(dictionary))
    window.snippets_editor.setPlainText("sig=Best regards")
    window.app_profiles_editor.setPlainText(json.dumps(profiles))

    assert window.apply_changes() is True
    assert json.loads((tmp_path / "glossary.json").read_text(encoding="utf-8")) == dictionary
    assert (tmp_path / "snippets.txt").read_text(encoding="utf-8") == "sig=Best regards\n"
    assert json.loads((tmp_path / "app_profiles.json").read_text(encoding="utf-8")) == profiles


def test_windows_autostart_manager_uses_hkcu_run_key():
    from voicetray.ui.settings_window import WindowsAutoStartManager

    class FakeRegistry:
        HKEY_CURRENT_USER = "HKCU"
        REG_SZ = "REG_SZ"
        values = {}

        def CreateKey(self, root, path):
            self.values.setdefault((root, path), {})
            return (root, path)

        def OpenKey(self, root, path, *_args):
            return (root, path)

        def SetValueEx(self, key, name, _reserved, kind, value):
            self.values.setdefault(key, {})[name] = (kind, value)

        def QueryValueEx(self, key, name):
            return self.values[key][name]

        def DeleteValue(self, key, name):
            del self.values[key][name]

        def CloseKey(self, _key):
            return None

    fake_registry = FakeRegistry()
    manager = WindowsAutoStartManager(
        registry=fake_registry,
        platform="win32",
        command="pythonw -m voicetray",
    )

    manager.set_enabled(True)
    assert manager.is_enabled() is True
    manager.set_enabled(False)
    assert manager.is_enabled() is False


def test_windows_autostart_manager_uses_frozen_exe_command(monkeypatch, tmp_path):
    import sys

    from voicetray.ui.settings_window import WindowsAutoStartManager

    exe = tmp_path / "VoiceTray.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))

    manager = WindowsAutoStartManager(platform="win32")

    assert manager.command == f'"{exe}"'
