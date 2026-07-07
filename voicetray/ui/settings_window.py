"""In-process PySide6 settings window."""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from voicetray.config import load_config, save_config

logger = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_RUN_VALUE = "VoiceTray"

MODES = ("raw", "balanced", "aggressive")
PROFILES = ("general", "email", "chat", "notes", "code/comments")
MODEL_SIZES = ("base", "small", "medium")
LANGUAGES = ("auto", "en", "es", "fr", "de", "it", "pt", "ja", "ko", "zh")


class WindowsAutoStartManager:
    def __init__(
        self,
        *,
        registry=None,
        platform: str | None = None,
        command: str | None = None,
    ):
        self.platform = sys.platform if platform is None else platform
        self.registry = registry
        self.command = command or self.default_command()

    def default_command(self) -> str:
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'
        executable = Path(sys.executable)
        pythonw = executable.with_name("pythonw.exe")
        launcher = pythonw if pythonw.exists() else executable
        return f'"{launcher}" -m voicetray'

    def is_enabled(self) -> bool:
        if self.platform != "win32":
            return False
        registry = self._registry()
        try:
            key = registry.OpenKey(registry.HKEY_CURRENT_USER, RUN_KEY, 0, getattr(registry, "KEY_READ", 0))
            try:
                value, _kind = registry.QueryValueEx(key, APP_RUN_VALUE)
                return bool(value)
            finally:
                registry.CloseKey(key)
        except OSError:
            return False
        except KeyError:
            return False

    def set_enabled(self, enabled: bool) -> None:
        if self.platform != "win32":
            return
        registry = self._registry()
        key = registry.CreateKey(registry.HKEY_CURRENT_USER, RUN_KEY)
        try:
            if enabled:
                registry.SetValueEx(key, APP_RUN_VALUE, 0, registry.REG_SZ, self.command)
            else:
                try:
                    registry.DeleteValue(key, APP_RUN_VALUE)
                except OSError:
                    pass
                except KeyError:
                    pass
        finally:
            registry.CloseKey(key)

    def _registry(self):
        if self.registry is not None:
            return self.registry
        import winreg

        return winreg


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_project_path(value: str | os.PathLike[str], *, base: Path | None = None) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base or project_root()) / path


def find_hotkey_conflicts(hotkeys: dict[str, str]) -> list[str]:
    seen: dict[str, str] = {}
    conflicts: list[str] = []
    for name in ("speech", "speech_alternative", "save", "cancel"):
        value = " ".join(str(hotkeys.get(name, "")).lower().split())
        if not value:
            continue
        if value in seen:
            conflicts.append(f"{seen[value]} and {name} both use {value}")
        else:
            seen[value] = name
    return conflicts


class SettingsWindow(QtWidgets.QDialog):
    def __init__(
        self,
        *,
        qt_modules=None,
        config_path: str | os.PathLike[str] | None = None,
        snippets_path: str | os.PathLike[str] | None = None,
        autostart_manager: WindowsAutoStartManager | None = None,
        on_config_applied: Callable[[dict[str, Any]], None] | None = None,
        model_download_callback: Callable[[str, Callable[[int], None]], None] | None = None,
    ):
        super().__init__()
        self.qt = qt_modules
        self.config_path = Path(config_path) if config_path is not None else None
        self.autostart_manager = autostart_manager or WindowsAutoStartManager()
        self.on_config_applied = on_config_applied
        self.model_download_callback = model_download_callback
        self.config = load_config(config_path=self.config_path)
        self.snippets_path = Path(snippets_path) if snippets_path is not None else resolve_project_path("snippets.txt")
        self.glossary_path = resolve_project_path(self.config["dictation"]["glossary_path"])
        self.app_profiles_path = resolve_project_path(self.config["dictation"]["app_profiles_path"])

        self.setWindowTitle("VoiceTray Settings")
        self.setMinimumSize(760, 560)
        self.tabs = QtWidgets.QTabWidget(self)
        self.status_label = QtWidgets.QLabel("", self)
        self.apply_button = QtWidgets.QPushButton("Apply", self)
        self.close_button = QtWidgets.QPushButton("Close", self)
        self.apply_button.clicked.connect(self.apply_changes)
        self.close_button.clicked.connect(self.close)

        self._build()
        self._load_values()

    def _build(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.tabs)

        footer = QtWidgets.QHBoxLayout()
        footer.addWidget(self.status_label, 1)
        footer.addWidget(self.apply_button)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)

        self.tabs.addTab(self._general_tab(), "General")
        self.tabs.addTab(self._cleanup_tab(), "Cleanup")
        self.tabs.addTab(self._dictionary_tab(), "Dictionary")
        self.tabs.addTab(self._snippets_tab(), "Snippets")
        self.tabs.addTab(self._models_tab(), "Models")
        self.tabs.addTab(self._about_tab(), "About")

    def _general_tab(self):
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        self.speech_hotkey_edit = QtWidgets.QLineEdit()
        self.alternative_hotkey_edit = QtWidgets.QLineEdit()
        self.save_hotkey_edit = QtWidgets.QLineEdit()
        self.cancel_hotkey_edit = QtWidgets.QLineEdit()
        self.tap_lock_spin = QtWidgets.QSpinBox()
        self.tap_lock_spin.setRange(100, 2000)
        self.tap_lock_spin.setSuffix(" ms")
        self.autostart_checkbox = QtWidgets.QCheckBox()
        self.auto_listen_checkbox = QtWidgets.QCheckBox()
        self.notification_spin = QtWidgets.QSpinBox()
        self.notification_spin.setRange(1, 30)
        self.notification_spin.setSuffix(" s")
        self.language_combo = QtWidgets.QComboBox()
        self.language_combo.addItems(LANGUAGES)

        form.addRow("Speech hotkey", self.speech_hotkey_edit)
        form.addRow("Alternate hotkey", self.alternative_hotkey_edit)
        form.addRow("Save hotkey", self.save_hotkey_edit)
        form.addRow("Cancel hotkey", self.cancel_hotkey_edit)
        form.addRow("Tap lock threshold", self.tap_lock_spin)
        form.addRow("Start with Windows", self.autostart_checkbox)
        form.addRow("Auto-start listening", self.auto_listen_checkbox)
        form.addRow("Notification duration", self.notification_spin)
        form.addRow("Language", self.language_combo)
        return page

    def _cleanup_tab(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        form = QtWidgets.QFormLayout()
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(MODES)
        self.profile_combo = QtWidgets.QComboBox()
        self.profile_combo.addItems(PROFILES)
        self.max_seconds_spin = QtWidgets.QSpinBox()
        self.max_seconds_spin.setRange(10, 3600)
        self.max_seconds_spin.setSuffix(" s")
        self.warning_seconds_spin = QtWidgets.QSpinBox()
        self.warning_seconds_spin.setRange(0, 3600)
        self.warning_seconds_spin.setSuffix(" s")
        form.addRow("Cleanup mode", self.mode_combo)
        form.addRow("Default profile", self.profile_combo)
        form.addRow("Recording cap", self.max_seconds_spin)
        form.addRow("Warning time", self.warning_seconds_spin)
        layout.addLayout(form)
        self.app_profiles_editor = QtWidgets.QPlainTextEdit()
        self.app_profiles_editor.setObjectName("appProfilesEditor")
        layout.addWidget(QtWidgets.QLabel("Per-app profile JSON"))
        layout.addWidget(self.app_profiles_editor, 1)
        return page

    def _dictionary_tab(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        self.dictionary_editor = QtWidgets.QPlainTextEdit()
        self.dictionary_editor.setObjectName("dictionaryEditor")
        layout.addWidget(self.dictionary_editor)
        return page

    def _snippets_tab(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        self.snippets_editor = QtWidgets.QPlainTextEdit()
        self.snippets_editor.setObjectName("snippetsEditor")
        layout.addWidget(self.snippets_editor)
        return page

    def _models_tab(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        form = QtWidgets.QFormLayout()
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.addItems(MODEL_SIZES)
        self.device_combo = QtWidgets.QComboBox()
        self.device_combo.addItems(("cpu", "cuda", "auto"))
        self.compute_combo = QtWidgets.QComboBox()
        self.compute_combo.addItems(("int8", "float16", "float32"))
        self.local_files_checkbox = QtWidgets.QCheckBox()
        self.llm_enabled_checkbox = QtWidgets.QCheckBox()
        self.llm_path_edit = QtWidgets.QLineEdit()
        self.model_progress = QtWidgets.QProgressBar()
        self.model_progress.setRange(0, 100)
        self.model_progress.setValue(0)
        self.download_button = QtWidgets.QPushButton("Download")
        self.download_button.clicked.connect(self.download_selected_model)
        self.llm_link_button = QtWidgets.QPushButton("Open LLM Link")
        self.llm_link_button.clicked.connect(self.open_llm_download_link)

        form.addRow("Whisper model", self.model_combo)
        form.addRow("Device", self.device_combo)
        form.addRow("Compute type", self.compute_combo)
        form.addRow("Use local model files only", self.local_files_checkbox)
        form.addRow("Enable local LLM cleanup", self.llm_enabled_checkbox)
        form.addRow("GGUF model path", self.llm_path_edit)
        form.addRow("Model download", self.download_button)
        form.addRow("LLM model link", self.llm_link_button)
        form.addRow("Progress", self.model_progress)
        layout.addLayout(form)
        return page

    def _about_tab(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        label = QtWidgets.QLabel("VoiceTray")
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setObjectName("aboutTitle")
        layout.addStretch(1)
        layout.addWidget(label)
        layout.addStretch(1)
        return page

    def _load_values(self) -> None:
        cfg = self.config
        self.speech_hotkey_edit.setText(cfg["hotkeys"]["speech"])
        self.alternative_hotkey_edit.setText(cfg["hotkeys"]["speech_alternative"])
        self.save_hotkey_edit.setText(cfg["hotkeys"]["save"])
        self.cancel_hotkey_edit.setText(cfg["hotkeys"]["cancel"])
        self.tap_lock_spin.setValue(int(cfg["hotkeys"]["tap_lock_ms"]))
        self.autostart_checkbox.setChecked(bool(cfg["app"]["start_with_windows"] or self.autostart_manager.is_enabled()))
        self.auto_listen_checkbox.setChecked(bool(cfg["app"]["auto_start_listening"]))
        self.notification_spin.setValue(int(cfg["app"]["notification_duration"]))
        self._set_combo(self.language_combo, cfg["stt"]["language"])
        self._set_combo(self.mode_combo, cfg["dictation"]["mode"])
        self._set_combo(self.profile_combo, cfg["dictation"]["profile"])
        self.max_seconds_spin.setValue(int(cfg["recording"]["max_seconds"]))
        self.warning_seconds_spin.setValue(int(cfg["recording"]["warning_seconds"]))
        self._set_combo(self.model_combo, cfg["stt"]["model_size"])
        self._set_combo(self.device_combo, cfg["stt"]["device"])
        self._set_combo(self.compute_combo, cfg["stt"]["compute_type"])
        self.local_files_checkbox.setChecked(bool(cfg["stt"]["local_files_only"]))
        self.llm_enabled_checkbox.setChecked(bool(cfg["llm"]["enabled"]))
        self.llm_path_edit.setText(cfg["llm"]["model_path"])
        self.dictionary_editor.setPlainText(self._read_text(self.glossary_path, default='{"user_terms": [], "protected_terms": [], "replacements": {}}\n'))
        self.snippets_editor.setPlainText(self._read_text(self.snippets_path))
        self.app_profiles_editor.setPlainText(self._read_text(self.app_profiles_path, default="[]\n"))

    def _set_combo(self, combo: QtWidgets.QComboBox, value: str) -> None:
        if combo.findText(value) < 0:
            combo.addItem(value)
        combo.setCurrentText(value)

    def apply_changes(self) -> bool:
        try:
            cfg = self._collect_config()
            conflicts = find_hotkey_conflicts(cfg["hotkeys"])
            if conflicts:
                self.status_label.setText("Hotkey conflict: " + "; ".join(conflicts))
                return False

            dictionary = self._parse_json_editor(self.dictionary_editor, dict, "Dictionary")
            profiles = self._parse_json_editor(self.app_profiles_editor, list, "Per-app profiles")
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return False

        saved = save_config(cfg, self.config_path)
        self._write_json(self.glossary_path, dictionary)
        self._write_text(self.snippets_path, self._normalized_plain_text(self.snippets_editor))
        self._write_json(self.app_profiles_path, profiles)
        self.autostart_manager.set_enabled(saved["app"]["start_with_windows"])
        self.config = saved
        if self.on_config_applied is not None:
            self.on_config_applied(saved)
        self.status_label.setText("Saved")
        return True

    def _collect_config(self) -> dict[str, Any]:
        cfg = json.loads(json.dumps(self.config))
        cfg["hotkeys"]["speech"] = self.speech_hotkey_edit.text().strip()
        cfg["hotkeys"]["speech_alternative"] = self.alternative_hotkey_edit.text().strip()
        cfg["hotkeys"]["save"] = self.save_hotkey_edit.text().strip()
        cfg["hotkeys"]["cancel"] = self.cancel_hotkey_edit.text().strip()
        cfg["hotkeys"]["tap_lock_ms"] = int(self.tap_lock_spin.value())
        cfg["app"]["start_with_windows"] = bool(self.autostart_checkbox.isChecked())
        cfg["app"]["auto_start_listening"] = bool(self.auto_listen_checkbox.isChecked())
        cfg["app"]["notification_duration"] = int(self.notification_spin.value())
        cfg["recording"]["max_seconds"] = int(self.max_seconds_spin.value())
        cfg["recording"]["warning_seconds"] = int(self.warning_seconds_spin.value())
        cfg["dictation"]["mode"] = self.mode_combo.currentText()
        cfg["dictation"]["profile"] = self.profile_combo.currentText()
        cfg["stt"]["language"] = self.language_combo.currentText()
        cfg["stt"]["model_size"] = self.model_combo.currentText()
        cfg["stt"]["device"] = self.device_combo.currentText()
        cfg["stt"]["compute_type"] = self.compute_combo.currentText()
        cfg["stt"]["local_files_only"] = bool(self.local_files_checkbox.isChecked())
        cfg["llm"]["enabled"] = bool(self.llm_enabled_checkbox.isChecked())
        cfg["llm"]["model_path"] = self.llm_path_edit.text().strip()
        return cfg

    def download_selected_model(self) -> None:
        self.model_progress.setValue(5)
        model_size = self.model_combo.currentText()
        if self.model_download_callback is None:
            self.model_progress.setValue(100)
            self.status_label.setText(f"{model_size} selected")
            return
        try:
            self.model_download_callback(model_size, self.model_progress.setValue)
            self.model_progress.setValue(100)
            self.status_label.setText(f"{model_size} ready")
        except Exception:
            logger.exception("Model download failed")
            self.status_label.setText(f"Could not download {model_size}")

    def open_llm_download_link(self) -> None:
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl("https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF")
        )

    def show_tab(self, tab_name: str | None) -> None:
        if not tab_name:
            return
        target = str(tab_name).strip().lower()
        aliases = {"llm": "models", "model": "models", "help": "about"}
        target = aliases.get(target, target)
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index).lower() == target:
                self.tabs.setCurrentIndex(index)
                return

    def _parse_json_editor(self, editor: QtWidgets.QPlainTextEdit, expected_type: type, label: str):
        try:
            value = json.loads(editor.toPlainText() or "null")
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} JSON error: {exc.msg}") from exc
        if not isinstance(value, expected_type):
            raise ValueError(f"{label} must be {expected_type.__name__}")
        return value

    def _read_text(self, path: Path, default: str = "") -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return default

    def _write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_json(self, path: Path, value: Any) -> None:
        self._write_text(path, json.dumps(value, indent=2) + "\n")

    def _normalized_plain_text(self, editor: QtWidgets.QPlainTextEdit) -> str:
        text = editor.toPlainText().rstrip()
        return text + "\n" if text else ""
