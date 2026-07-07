"""First-run PySide6 onboarding wizard."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtWidgets

from voicetray.config import load_config, save_config

logger = logging.getLogger(__name__)

MODEL_SIZES = ("base", "small", "medium")


class OnboardingWizard(QtWidgets.QWizard):
    PAGE_WELCOME = 0
    PAGE_MIC = 1
    PAGE_MODEL = 2
    PAGE_HOTKEY = 3
    PAGE_DONE = 4

    def __init__(
        self,
        *,
        qt_modules=None,
        config_path: str | os.PathLike[str] | None = None,
        on_config_applied: Callable[[dict[str, Any]], None] | None = None,
        model_download_callback: Callable[[str, Callable[[int], None]], None] | None = None,
        hotkey_hint: str | None = None,
    ):
        super().__init__()
        self.qt = qt_modules
        self.config_path = Path(config_path) if config_path is not None else None
        self.on_config_applied = on_config_applied
        self.model_download_callback = model_download_callback
        self.config = load_config(config_path=self.config_path)
        self.hotkey_hint = hotkey_hint or str(self.config["hotkeys"]["speech"]).upper()

        self.setWindowTitle("VoiceTray Setup")
        self.setMinimumSize(640, 440)
        self.setOption(QtWidgets.QWizard.NoBackButtonOnStartPage, True)

        self.addPage(self._welcome_page())
        self.addPage(self._microphone_page())
        self.addPage(self._model_page())
        self.addPage(self._hotkey_page())
        self.addPage(self._done_page())

    def _welcome_page(self) -> QtWidgets.QWizardPage:
        page = QtWidgets.QWizardPage()
        page.setTitle("Welcome")
        layout = QtWidgets.QVBoxLayout(page)
        title = QtWidgets.QLabel("VoiceTray")
        title.setObjectName("onboardingTitle")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: 600;")
        subtitle = QtWidgets.QLabel("Offline dictation that stays in your tray.")
        subtitle.setAlignment(QtCore.Qt.AlignCenter)
        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch(1)
        return page

    def _microphone_page(self) -> QtWidgets.QWizardPage:
        page = QtWidgets.QWizardPage()
        page.setTitle("Microphone")
        layout = QtWidgets.QVBoxLayout(page)
        self.level_bar = QtWidgets.QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setValue(0)
        self.mic_status_label = QtWidgets.QLabel("Waiting for microphone signal")
        self.mic_status_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(QtWidgets.QLabel("Speak briefly and watch the level move."))
        layout.addWidget(self.level_bar)
        layout.addWidget(self.mic_status_label)
        layout.addStretch(1)
        return page

    def _model_page(self) -> QtWidgets.QWizardPage:
        page = QtWidgets.QWizardPage()
        page.setTitle("Model")
        layout = QtWidgets.QVBoxLayout(page)
        form = QtWidgets.QFormLayout()
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.addItems(MODEL_SIZES)
        if self.config["stt"]["model_size"] not in MODEL_SIZES:
            self.model_combo.addItem(self.config["stt"]["model_size"])
        self.model_combo.setCurrentText(self.config["stt"]["model_size"])
        self.model_progress = QtWidgets.QProgressBar()
        self.model_progress.setRange(0, 100)
        self.model_progress.setValue(0)
        self.download_button = QtWidgets.QPushButton("Download")
        self.download_button.clicked.connect(self.download_selected_model)
        self.model_status_label = QtWidgets.QLabel("")
        form.addRow("Whisper model", self.model_combo)
        form.addRow("Model download", self.download_button)
        form.addRow("Progress", self.model_progress)
        layout.addLayout(form)
        layout.addWidget(self.model_status_label)
        layout.addStretch(1)
        return page

    def _hotkey_page(self) -> QtWidgets.QWizardPage:
        page = QtWidgets.QWizardPage()
        page.setTitle("Hotkey")
        layout = QtWidgets.QVBoxLayout(page)
        self.hotkey_hint_label = QtWidgets.QLabel(self.hotkey_hint)
        self.hotkey_hint_label.setObjectName("hotkeyHint")
        self.hotkey_hint_label.setAlignment(QtCore.Qt.AlignCenter)
        self.hotkey_hint_label.setStyleSheet("font-size: 24px; font-weight: 600;")
        self.hotkey_test_field = QtWidgets.QPlainTextEdit()
        self.hotkey_test_field.setPlaceholderText("Dictated text appears here during the tutorial")
        self.hotkey_test_field.textChanged.connect(self._update_hotkey_status)
        self.hotkey_status_label = QtWidgets.QLabel("Waiting for tutorial text")
        self.hotkey_status_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(QtWidgets.QLabel("Hold the speech hotkey and dictate into this field."))
        layout.addWidget(self.hotkey_hint_label)
        layout.addWidget(self.hotkey_test_field, 1)
        layout.addWidget(self.hotkey_status_label)
        return page

    def _done_page(self) -> QtWidgets.QWizardPage:
        page = QtWidgets.QWizardPage()
        page.setTitle("Done")
        layout = QtWidgets.QVBoxLayout(page)
        self.finish_status_label = QtWidgets.QLabel("Ready to dictate")
        self.finish_status_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addStretch(1)
        layout.addWidget(self.finish_status_label)
        layout.addStretch(1)
        return page

    def update_audio_level(self, level: float) -> None:
        value = int(max(0.0, min(1.0, float(level))) * 100)
        self.level_bar.setValue(value)
        if value > 0:
            self.mic_status_label.setText("Microphone signal detected")
        else:
            self.mic_status_label.setText("Waiting for microphone signal")

    def download_selected_model(self) -> None:
        model_size = self.model_combo.currentText()
        self.model_progress.setValue(5)
        self.model_status_label.setText(f"Preparing {model_size}")
        if self.model_download_callback is None:
            self.model_progress.setValue(100)
            self.model_status_label.setText(f"{model_size} ready")
            return
        try:
            self.model_download_callback(model_size, self.update_model_download_progress)
            self.model_progress.setValue(100)
            self.model_status_label.setText(f"{model_size} ready")
        except Exception:
            logger.exception("Onboarding model download failed")
            self.model_status_label.setText(f"Could not download {model_size}")

    def update_model_download_progress(self, value: int) -> None:
        self.model_progress.setValue(max(0, min(100, int(value))))

    def finish_onboarding(self) -> bool:
        cfg = json.loads(json.dumps(self.config))
        cfg["app"]["onboarded"] = True
        cfg["stt"]["model_size"] = self.model_combo.currentText()
        saved = save_config(cfg, self.config_path)
        self.config = saved
        self.finish_status_label.setText("Ready to dictate")
        if self.on_config_applied is not None:
            self.on_config_applied(saved)
        return True

    def accept(self) -> None:
        self.finish_onboarding()
        super().accept()

    def _update_hotkey_status(self) -> None:
        if self.hotkey_test_field.toPlainText().strip():
            self.hotkey_status_label.setText("Tutorial text received")
        else:
            self.hotkey_status_label.setText("Waiting for tutorial text")
