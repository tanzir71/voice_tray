"""Qt application shell for VoiceTray."""

from __future__ import annotations

import logging
import sys
from types import SimpleNamespace
from typing import Callable, Sequence

from .config import load_config
from .crash_guard import install_crash_guard
from .model_download import download_whisper_model
from .ui.history_window import HistoryWindow
from .ui.onboarding import OnboardingWizard
from .ui.pill import VoiceTrayPill
from .ui.settings_window import SettingsWindow
from .ui.tray import TrayCallbacks, TrayState, VoiceTrayTray

logger = logging.getLogger(__name__)


def _load_qt_modules():
    from PySide6 import QtCore, QtGui, QtWidgets

    return SimpleNamespace(QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets)


def create_worker_signals(QtCore):
    class VoiceTrayWorkerSignals(QtCore.QObject):
        recording_started = QtCore.Signal()
        recording_stopped = QtCore.Signal(float)
        audio_level_changed = QtCore.Signal(float)
        processing_started = QtCore.Signal()
        processing_finished = QtCore.Signal(str)
        error = QtCore.Signal(str)
        notification_requested = QtCore.Signal(str)

    return VoiceTrayWorkerSignals()


class LegacyWorkerController:
    """Bridge the current dictation worker into the Qt-owned process."""

    def __init__(self, signals):
        self.signals = signals
        self.core = None

    def start(self) -> None:
        from .legacy_app import VoiceTrayApp as CoreVoiceTrayApp

        self.core = CoreVoiceTrayApp()
        self.core.notification_callback = self.signals.notification_requested.emit
        self.core.recording_started_callback = self.signals.recording_started.emit
        self.core.recording_stopped_callback = self.signals.recording_stopped.emit
        self.core.processing_started_callback = self.signals.processing_started.emit
        self.core.processing_finished_callback = self.signals.processing_finished.emit
        self.core.error_callback = self.signals.error.emit
        self.core.audio_level_callback = self.signals.audio_level_changed.emit
        if getattr(self.core, "audio_recorder", None) is not None:
            self.core.audio_recorder.level_callback = self.signals.audio_level_changed.emit
        self.core.start_second_launch_notification_watcher()

        if getattr(self.core, "auto_start_listening", True):
            self.core.start_listening()

    def stop(self) -> None:
        if self.core is None:
            return

        self.core.cleanup()
        self.core = None

    def start_listening(self) -> None:
        if self.core is not None:
            self.core.start_listening()

    def stop_listening(self) -> None:
        if self.core is not None:
            self.core.stop_listening()

    def is_listening(self) -> bool:
        return bool(getattr(self.core, "is_listening", False))

    def model_label(self) -> str:
        if self.core is not None:
            config = getattr(self.core, "stt_config", None)
            model_size = getattr(config, "model_size", None)
            if model_size:
                return str(model_size)
        try:
            return str(load_config().get("stt", {}).get("model_size", "base"))
        except Exception:
            logger.debug("Could not load model label from config", exc_info=True)
            return "base"

    def hotkey_hint(self) -> str:
        if self.core is not None:
            hotkey = getattr(self.core, "hotkey", None)
            if hotkey:
                return str(hotkey).upper()
        try:
            return str(load_config().get("hotkeys", {}).get("speech", "F9")).upper()
        except Exception:
            logger.debug("Could not load hotkey hint from config", exc_info=True)
            return "F9"

    def history_store(self):
        if self.core is not None:
            return getattr(self.core, "history_store", None)
        return None

    def reinsert_text(self, text: str) -> None:
        if self.core is None:
            return
        inserter = getattr(self.core, "inserter", None)
        if inserter is None:
            return
        result = inserter.insert_text(
            text,
            start_focus=self.core.get_active_window_identity(),
            app_title=self.core.get_active_window_title(),
        )
        if getattr(result, "status", None) != "inserted":
            self.signals.notification_requested.emit("Could not re-insert text; copied in History.")

    def apply_config(self, config: dict) -> None:
        if self.core is None:
            return
        was_listening = bool(getattr(self.core, "is_listening", False))
        if was_listening:
            self.core.stop_listening()
        self.core.load_settings()
        self.core.load_app_profiles()
        self.core.load_snippets_from_file()
        self.core.init_dictation_pipeline()
        self.core.init_speech_engine()
        self.core.audio_level_callback = self.signals.audio_level_changed.emit
        if getattr(self.core, "audio_recorder", None) is not None:
            self.core.audio_recorder.level_callback = self.signals.audio_level_changed.emit
        self.core.init_hotkey_controller()
        if was_listening:
            self.core.start_listening()


class VoiceTrayApp:
    """Own the Qt event loop and worker signal wiring."""

    def __init__(
        self,
        argv: Sequence[str] | None = None,
        qt_modules=None,
        controller_factory: Callable[[object], object] | None = None,
        tray_factory: Callable[..., object] | None = None,
        pill_factory: Callable[..., object] | None = None,
        settings_window_factory: Callable[..., object] | None = None,
        history_window_factory: Callable[..., object] | None = None,
        onboarding_window_factory: Callable[..., object] | None = None,
        config_loader: Callable[..., dict] | None = None,
        config_path=None,
        model_download_callback: Callable[[str, Callable[[int], None]], None] | None = None,
        crash_guard_installer: Callable[..., object] | None = None,
    ):
        self.argv = list(sys.argv if argv is None else argv)
        self.qt_modules = qt_modules
        self.controller_factory = controller_factory or LegacyWorkerController
        self.tray_factory = tray_factory or VoiceTrayTray
        self.pill_factory = pill_factory or VoiceTrayPill
        self.settings_window_factory = settings_window_factory or SettingsWindow
        self.history_window_factory = history_window_factory or HistoryWindow
        self.onboarding_window_factory = onboarding_window_factory or OnboardingWizard
        self.config_loader = config_loader or load_config
        self.config_path = config_path
        self.model_download_callback = model_download_callback or download_whisper_model
        self.crash_guard_installer = crash_guard_installer or install_crash_guard
        self.qt_app = None
        self.signals = None
        self.controller = None
        self.tray = None
        self.pill = None
        self.settings_window = None
        self.history_window = None
        self.onboarding_window = None
        self.config = None
        self.crash_guard = None

    def run(self) -> int:
        qt_modules = self.qt_modules or _load_qt_modules()
        application = qt_modules.QtWidgets.QApplication.instance()
        if application is None:
            application = qt_modules.QtWidgets.QApplication(self.argv)

        application.setApplicationName("VoiceTray")
        application.setQuitOnLastWindowClosed(False)

        self.qt_app = application
        self.config = self._load_app_config()
        self.signals = create_worker_signals(qt_modules.QtCore)
        self.controller = self.controller_factory(self.signals)
        self.tray = self.tray_factory(
            qt_modules=qt_modules,
            callbacks=TrayCallbacks(
                start_listening=self._start_listening,
                stop_listening=self._stop_listening,
                show_history=self._show_history,
                show_settings=self._show_settings,
                quit_app=getattr(application, "quit", lambda: None),
            ),
            model_label=self._controller_model_label(),
        )
        self.pill = self.pill_factory(
            qt_modules=qt_modules,
            hotkey_hint=self._controller_hotkey_hint(),
        )

        about_to_quit = getattr(application, "aboutToQuit", None)
        if about_to_quit is not None:
            about_to_quit.connect(self.controller.stop)

        self.signals.recording_started.connect(
            lambda: self.tray.set_state(TrayState.RECORDING)
        )
        self.signals.recording_started.connect(self.pill.show_recording)
        self.signals.audio_level_changed.connect(self.pill.update_level)
        self.signals.processing_started.connect(
            lambda: self.tray.set_state(TrayState.PROCESSING)
        )
        self.signals.processing_started.connect(self.pill.show_processing)
        self.signals.processing_finished.connect(
            lambda _text: self.tray.set_state(TrayState.IDLE)
        )
        self.signals.processing_finished.connect(lambda _text: self.pill.finish_success())
        self.signals.notification_requested.connect(self._log_notification)
        self.signals.notification_requested.connect(self.tray.show_notification)
        self.signals.error.connect(self._log_error)
        self.signals.error.connect(self._set_error_state)
        self.signals.error.connect(self.pill.show_error)

        self.crash_guard = self.crash_guard_installer(
            notify=self.signals.notification_requested.emit
        )
        self.controller.start()
        self._sync_listening_state()
        if hasattr(self.tray, "set_model_label"):
            self.tray.set_model_label(self._controller_model_label())
        self._show_onboarding_if_needed()
        return int(application.exec())

    def _log_notification(self, message: str) -> None:
        logger.info("Notification requested: %s", message)

    def _log_error(self, message: str) -> None:
        logger.error("Worker error: %s", message)

    def _set_error_state(self, message: str) -> None:
        if "microphone" in str(message).lower():
            self.tray.set_state(TrayState.NO_MICROPHONE)
            return
        self.tray.set_state(TrayState.IDLE)

    def _start_listening(self) -> None:
        if hasattr(self.controller, "start_listening"):
            self.controller.start_listening()
        self.tray.set_listening(True)

    def _stop_listening(self) -> None:
        if hasattr(self.controller, "stop_listening"):
            self.controller.stop_listening()
        self.tray.set_listening(False)

    def _show_history(self) -> None:
        if self.history_window is None:
            self.history_window = self.history_window_factory(
                qt_modules=self.qt_modules,
                store=self._controller_history_store(),
                reinsert_callback=self._reinsert_history_text,
            )
        self.history_window.refresh()
        self.history_window.show()
        self.history_window.raise_()
        self.history_window.activateWindow()

    def _show_settings(self) -> None:
        if self.settings_window is None:
            self.settings_window = self.settings_window_factory(
                qt_modules=self.qt_modules,
                on_config_applied=self._on_settings_applied,
                model_download_callback=self.model_download_callback,
            )
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _show_onboarding_if_needed(self) -> None:
        cfg = self.config if isinstance(self.config, dict) else {}
        if bool(cfg.get("app", {}).get("onboarded", False)):
            return
        self._show_onboarding()

    def _show_onboarding(self) -> None:
        if self.onboarding_window is None:
            self.onboarding_window = self.onboarding_window_factory(
                qt_modules=self.qt_modules,
                config_path=self.config_path,
                on_config_applied=self._on_onboarding_applied,
                model_download_callback=self.model_download_callback,
                hotkey_hint=self._controller_hotkey_hint(),
            )
            if hasattr(self.onboarding_window, "update_audio_level"):
                self.signals.audio_level_changed.connect(self.onboarding_window.update_audio_level)
        self.onboarding_window.show()
        self.onboarding_window.raise_()
        self.onboarding_window.activateWindow()

    def _on_settings_applied(self, config: dict) -> None:
        self.config = config
        if hasattr(self.controller, "apply_config"):
            self.controller.apply_config(config)
        if hasattr(self.tray, "set_model_label"):
            self.tray.set_model_label(self._controller_model_label())
        if hasattr(self.pill, "set_hotkey_hint"):
            self.pill.set_hotkey_hint(str(config.get("hotkeys", {}).get("speech", "F9")).upper())

    def _on_onboarding_applied(self, config: dict) -> None:
        self._on_settings_applied(config)

    def _controller_history_store(self):
        if hasattr(self.controller, "history_store"):
            store = self.controller.history_store()
            if store is not None:
                return store
        return None

    def _reinsert_history_text(self, text: str, _row=None) -> None:
        if hasattr(self.controller, "reinsert_text"):
            self.controller.reinsert_text(text)

    def _controller_model_label(self) -> str:
        if hasattr(self.controller, "model_label"):
            return str(self.controller.model_label())
        return "base"

    def _controller_hotkey_hint(self) -> str:
        if hasattr(self.controller, "hotkey_hint"):
            return str(self.controller.hotkey_hint())
        return "F9"

    def _sync_listening_state(self) -> None:
        if hasattr(self.controller, "is_listening"):
            self.tray.set_listening(bool(self.controller.is_listening()))

    def _load_app_config(self) -> dict:
        try:
            return self.config_loader(config_path=self.config_path)
        except TypeError:
            return self.config_loader()
