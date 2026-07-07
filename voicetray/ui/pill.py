"""Floating recording and processing pill."""

from __future__ import annotations

import ctypes
import sys
import time
from collections.abc import Callable
from enum import Enum

from PySide6 import QtCore, QtGui, QtWidgets


class PillState(str, Enum):
    HIDDEN = "hidden"
    RECORDING = "recording"
    PROCESSING = "processing"
    ERROR = "error"


class LevelMeter(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = 0.0
        self.setFixedSize(128, 28)

    def set_level(self, rms: float) -> None:
        self.level = max(0.0, min(1.0, float(rms) * 8.0))
        self.update()

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        bar_count = 12
        gap = 4
        bar_width = (self.width() - (bar_count - 1) * gap) / bar_count
        active = max(1, round(self.level * bar_count))
        for index in range(bar_count):
            height_ratio = 0.25 + (index % 4) * 0.18
            if index < active:
                height_ratio += min(self.level, 1.0) * 0.25
            height = max(6, int(self.height() * min(height_ratio, 1.0)))
            x = int(index * (bar_width + gap))
            y = int((self.height() - height) / 2)
            color = QtGui.QColor("#22c55e" if index < active else "#475569")
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(
                QtCore.QRectF(x, y, bar_width, height),
                3,
                3,
            )


class VoiceTrayPill(QtWidgets.QWidget):
    def __init__(
        self,
        *,
        qt_modules=None,
        hotkey_hint: str = "F9",
        clock: Callable[[], float] = time.monotonic,
        screen_geometry_provider: Callable[[], QtCore.QRect] | None = None,
        focus_point_provider: Callable[[], QtCore.QPoint | None] | None = None,
        timer_single_shot: Callable[[int, Callable[[], None]], None] | None = None,
    ):
        flags = (
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.Tool
        )
        super().__init__(None, flags)
        self.qt = qt_modules
        self.hotkey_hint = str(hotkey_hint or "F9").upper()
        self.clock = clock
        self.screen_geometry_provider = screen_geometry_provider
        self.focus_point_provider = focus_point_provider or focused_window_center
        self.timer_single_shot = timer_single_shot or QtCore.QTimer.singleShot
        self.state = PillState.HIDDEN
        self.started_at = 0.0
        self.spinner_index = 0
        self.spinner_frames = ("|", "/", "-", "\\")

        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self.setWindowTitle("VoiceTray")
        self.setFixedSize(360, 76)

        self.elapsed_timer = QtCore.QTimer(self)
        self.elapsed_timer.setInterval(250)
        self.elapsed_timer.timeout.connect(self.refresh_elapsed)

        self.spinner_timer = QtCore.QTimer(self)
        self.spinner_timer.setInterval(120)
        self.spinner_timer.timeout.connect(self.advance_spinner)

        self.level_meter = LevelMeter(self)
        self.status_label = QtWidgets.QLabel("Recording", self)
        self.elapsed_label = QtWidgets.QLabel("0:00", self)
        self.hotkey_label = QtWidgets.QLabel(self.hotkey_hint, self)
        self.spinner_label = QtWidgets.QLabel(self.spinner_frames[0], self)
        self.dismiss_button = QtWidgets.QToolButton(self)
        self.dismiss_button.setText("x")
        self.dismiss_button.setAutoRaise(True)
        self.dismiss_button.clicked.connect(self.hide)

        self._build_layout()
        self._apply_normal_style()
        self.hide()

    def _build_layout(self) -> None:
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(18, 14, 12, 14)
        root.setSpacing(14)

        root.addWidget(self.level_meter)
        self.spinner_label.setFixedWidth(28)
        self.spinner_label.setAlignment(QtCore.Qt.AlignCenter)
        root.addWidget(self.spinner_label)

        text_layout = QtWidgets.QVBoxLayout()
        text_layout.setSpacing(2)
        self.status_label.setObjectName("status")
        self.elapsed_label.setObjectName("elapsed")
        text_layout.addWidget(self.status_label)
        text_layout.addWidget(self.elapsed_label)
        root.addLayout(text_layout, 1)

        self.hotkey_label.setObjectName("hotkey")
        self.hotkey_label.setAlignment(QtCore.Qt.AlignCenter)
        root.addWidget(self.hotkey_label)
        root.addWidget(self.dismiss_button)
        self.spinner_label.hide()

    def show_recording(self) -> None:
        self.state = PillState.RECORDING
        self.started_at = self.clock()
        self.spinner_timer.stop()
        self.level_meter.show()
        self.spinner_label.hide()
        self.hotkey_label.show()
        self.status_label.setText("Recording")
        self.update_level(0.0)
        self.refresh_elapsed()
        self._apply_normal_style()
        self._show_at_bottom_center()
        self.elapsed_timer.start()

    def set_hotkey_hint(self, hotkey_hint: str) -> None:
        self.hotkey_hint = str(hotkey_hint or "F9").upper()
        self.hotkey_label.setText(self.hotkey_hint)

    def update_level(self, rms: float) -> None:
        self.level_meter.set_level(rms)

    def refresh_elapsed(self) -> None:
        elapsed = max(0, int(round(self.clock() - self.started_at)))
        minutes, seconds = divmod(elapsed, 60)
        self.elapsed_label.setText(f"{minutes}:{seconds:02d}")

    def show_processing(self) -> None:
        self.state = PillState.PROCESSING
        self.elapsed_timer.stop()
        self.level_meter.hide()
        self.hotkey_label.hide()
        self.spinner_label.show()
        self.status_label.setText("Polishing...")
        self.elapsed_label.setText("Working locally")
        self._apply_normal_style()
        self._show_at_bottom_center()
        self.spinner_timer.start()

    def advance_spinner(self) -> None:
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_frames)
        self.spinner_label.setText(self.spinner_frames[self.spinner_index])

    def finish_success(self) -> None:
        self.state = PillState.HIDDEN
        self.elapsed_timer.stop()
        self.spinner_timer.stop()
        self.hide_after(650)

    def show_error(self, message: str) -> None:
        self.state = PillState.ERROR
        self.elapsed_timer.stop()
        self.spinner_timer.stop()
        self.level_meter.hide()
        self.spinner_label.hide()
        self.hotkey_label.hide()
        self.status_label.setText(str(message))
        self.elapsed_label.setText("Saved to history when possible")
        self._apply_error_style()
        self._show_at_bottom_center()
        self.hide_after(2200)

    def hide_after(self, milliseconds: int) -> None:
        self.timer_single_shot(int(milliseconds), self.hide)

    def _show_at_bottom_center(self) -> None:
        self._position_near_focused_window()
        self.show()
        self.raise_()

    def _position_near_focused_window(self) -> None:
        geometry = self._screen_geometry()
        x = geometry.x() + int((geometry.width() - self.width()) / 2)
        y = geometry.y() + geometry.height() - self.height() - 64
        self.move(x, y)

    def _screen_geometry(self) -> QtCore.QRect:
        if self.screen_geometry_provider is not None:
            return self.screen_geometry_provider()

        point = None
        if self.focus_point_provider is not None:
            point = self.focus_point_provider()

        screen = None
        if point is not None:
            screen = QtGui.QGuiApplication.screenAt(point)
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return QtCore.QRect(0, 0, 800, 600)
        return screen.availableGeometry()

    def _apply_normal_style(self) -> None:
        self.setStyleSheet(
            """
            VoiceTrayPill {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 22px;
            }
            QLabel {
                color: #e5e7eb;
                font-family: Segoe UI;
            }
            QLabel#status {
                font-size: 15px;
                font-weight: 600;
            }
            QLabel#elapsed {
                color: #94a3b8;
                font-size: 12px;
            }
            QLabel#hotkey {
                background: #1f2937;
                border: 1px solid #475569;
                border-radius: 10px;
                min-width: 48px;
                min-height: 28px;
                font-size: 12px;
                font-weight: 600;
            }
            QToolButton {
                color: #cbd5e1;
                border: none;
                min-width: 24px;
                min-height: 24px;
                font-weight: 700;
            }
            """
        )

    def _apply_error_style(self) -> None:
        self.setStyleSheet(
            """
            VoiceTrayPill {
                background: #b91c1c;
                border: 1px solid #fecaca;
                border-radius: 22px;
            }
            QLabel {
                color: #fff7ed;
                font-family: Segoe UI;
            }
            QLabel#status {
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#elapsed {
                color: #fee2e2;
                font-size: 12px;
            }
            QToolButton {
                color: #fff7ed;
                border: none;
                min-width: 24px;
                min-height: 24px;
                font-weight: 700;
            }
            """
        )


def focused_window_center() -> QtCore.QPoint | None:
    if sys.platform != "win32":
        return QtGui.QCursor.pos()

    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        rect = wintypes_RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return QtGui.QCursor.pos()
        return QtCore.QPoint(
            int((rect.left + rect.right) / 2),
            int((rect.top + rect.bottom) / 2),
        )
    except Exception:
        return QtGui.QCursor.pos()


class wintypes_RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]
