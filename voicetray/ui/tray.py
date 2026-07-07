"""Native Qt system tray UI."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from voicetray.logging_config import log_file_path

logger = logging.getLogger(__name__)


def _noop() -> None:
    return None


class TrayState(str, Enum):
    IDLE = "Idle"
    RECORDING = "Recording"
    PROCESSING = "Processing"
    NO_MICROPHONE = "No microphone"


@dataclass(frozen=True)
class TrayAssets:
    idle: Path
    recording: Path
    processing: Path

    def as_dict(self) -> dict[TrayState, Path]:
        return {
            TrayState.IDLE: self.idle,
            TrayState.RECORDING: self.recording,
            TrayState.PROCESSING: self.processing,
            TrayState.NO_MICROPHONE: self.idle,
        }


@dataclass(frozen=True)
class TrayCallbacks:
    start_listening: Callable[[], None] = field(default=_noop)
    stop_listening: Callable[[], None] = field(default=_noop)
    show_history: Callable[[], None] = field(default=_noop)
    show_settings: Callable[[], None] = field(default=_noop)
    quit_app: Callable[[], None] = field(default=_noop)


def default_asset_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "assets" / "tray"
    return Path(__file__).resolve().parents[2] / "assets" / "tray"


def default_tray_assets(asset_dir: str | Path | None = None) -> TrayAssets:
    base = Path(asset_dir) if asset_dir is not None else default_asset_dir()
    return TrayAssets(
        idle=base / "mic_idle.ico",
        recording=base / "mic_recording.ico",
        processing=base / "mic_processing.ico",
    )


class VoiceTrayTray:
    """Qt tray icon, state tooltip, notifications, and nonblocking menu."""

    def __init__(
        self,
        *,
        qt_modules,
        callbacks: TrayCallbacks | None = None,
        model_label: str = "base",
        log_dir: str | Path | None = None,
        assets: TrayAssets | None = None,
    ):
        self.qt = qt_modules
        self.callbacks = callbacks or TrayCallbacks()
        self.assets = assets or default_tray_assets()
        self.model_label = str(model_label or "base")
        self.state = TrayState.IDLE
        self.listening = False
        self.log_dir = Path(log_dir) if log_dir is not None else log_file_path().parent

        self.icons = {
            state: self.qt.QtGui.QIcon(str(path))
            for state, path in self.assets.as_dict().items()
        }
        self.menu = self.qt.QtWidgets.QMenu()
        self.tray_icon = self.qt.QtWidgets.QSystemTrayIcon(self.icons[self.state])
        self.tray_icon.setContextMenu(self.menu)

        self.toggle_action = None
        self._build_menu()
        self._refresh_tooltip()
        self.tray_icon.show()

    def _build_menu(self) -> None:
        self.toggle_action = self.menu.addAction("Start Listening")
        self.toggle_action.setCheckable(True)
        self.toggle_action.triggered.connect(
            lambda _checked=False: self._toggle_listening()
        )
        self.menu.addSeparator()

        history_action = self.menu.addAction("History...")
        history_action.triggered.connect(
            lambda _checked=False: self._defer(self.callbacks.show_history)
        )

        settings_action = self.menu.addAction("Settings...")
        settings_action.triggered.connect(
            lambda _checked=False: self._defer(self.callbacks.show_settings)
        )

        log_action = self.menu.addAction("Open Log Folder")
        log_action.triggered.connect(
            lambda _checked=False: self._defer(self.open_log_folder)
        )
        self.menu.addSeparator()

        quit_action = self.menu.addAction("Quit")
        quit_action.triggered.connect(
            lambda _checked=False: self._defer(self.callbacks.quit_app)
        )

    def _toggle_listening(self) -> None:
        callback = (
            self.callbacks.stop_listening
            if self.listening
            else self.callbacks.start_listening
        )
        self._defer(callback)

    def _defer(self, callback: Callable[[], None]) -> None:
        self.qt.QtCore.QTimer.singleShot(0, callback)

    def set_listening(self, value: bool) -> None:
        self.listening = bool(value)
        if self.toggle_action is None:
            return
        self.toggle_action.setText("Stop Listening" if self.listening else "Start Listening")
        self.toggle_action.setChecked(self.listening)

    def set_model_label(self, model_label: str) -> None:
        self.model_label = str(model_label or "base")
        self._refresh_tooltip()

    def set_state(self, state: TrayState) -> None:
        self.state = TrayState(state)
        self.tray_icon.setIcon(self.icons[self.state])
        self._refresh_tooltip()

    def show_notification(self, message: str, *, timeout_ms: int = 4000) -> None:
        message_icon = getattr(self.qt.QtWidgets.QSystemTrayIcon, "Information", None)
        if message_icon is None:
            message_icon = self.qt.QtWidgets.QSystemTrayIcon.MessageIcon.Information
        self.tray_icon.showMessage("VoiceTray", str(message), message_icon, timeout_ms)

    def open_log_folder(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        url = self.qt.QtCore.QUrl.fromLocalFile(str(self.log_dir))
        opened = self.qt.QtGui.QDesktopServices.openUrl(url)
        if not opened:
            logger.warning("Could not open log folder: %s", self.log_dir)

    def _refresh_tooltip(self) -> None:
        self.tray_icon.setToolTip(
            f"VoiceTray - {self.state.value} - model {self.model_label}"
        )
