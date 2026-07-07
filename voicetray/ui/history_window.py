"""PySide6 history window."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtWidgets

from voicetray.dictation.glossary import learn_word
from voicetray.history import DictationHistoryStore, HistoryRow


def add_word_to_dictionary_action(
    selected_text: str,
    *,
    glossary_path: str | os.PathLike[str] = "glossary.json",
) -> str | None:
    term = " ".join((selected_text or "").split())
    if not term:
        return None

    learn_word(glossary_path, term)
    return term


class HistoryWindow(QtWidgets.QDialog):
    def __init__(
        self,
        *,
        qt_modules=None,
        store: DictationHistoryStore | None = None,
        db_path: str | os.PathLike[str] | None = None,
        clipboard: Any | None = None,
        reinsert_callback: Callable[[str, HistoryRow], None] | Callable[[str], None] | None = None,
        glossary_path: str | os.PathLike[str] = "glossary.json",
        limit: int = 200,
    ):
        super().__init__()
        self.qt = qt_modules
        self.store = store or DictationHistoryStore(db_path)
        self.clipboard = clipboard
        self.reinsert_callback = reinsert_callback
        self.glossary_path = Path(glossary_path)
        self.limit = int(limit)
        self.rows: list[HistoryRow] = []
        self.filtered_rows: list[HistoryRow] = []

        self.setWindowTitle("VoiceTray History")
        self.setMinimumSize(860, 560)
        self.search_edit = QtWidgets.QLineEdit(self)
        self.search_edit.setPlaceholderText("Search history")
        self.list_widget = QtWidgets.QListWidget(self)
        self.detail_editor = QtWidgets.QPlainTextEdit(self)
        self.detail_editor.setReadOnly(True)
        self.raw_toggle = QtWidgets.QCheckBox("Show raw transcript", self)
        self.metadata_label = QtWidgets.QLabel("", self)
        self.copy_button = QtWidgets.QPushButton("Copy", self)
        self.reinsert_button = QtWidgets.QPushButton("Re-insert", self)
        self.add_dictionary_button = QtWidgets.QPushButton("Add Selection to Dictionary", self)
        self.status_label = QtWidgets.QLabel("", self)

        self._build_layout()
        self._connect_signals()
        self.refresh()

    def _build_layout(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.addWidget(self.search_edit)

        body = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.list_widget)

        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.metadata_label)
        right_layout.addWidget(self.raw_toggle)
        right_layout.addWidget(self.detail_editor, 1)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.reinsert_button)
        buttons.addWidget(self.add_dictionary_button)
        right_layout.addLayout(buttons)
        right_layout.addWidget(self.status_label)

        body.addWidget(left)
        body.addWidget(right)
        body.setStretchFactor(0, 1)
        body.setStretchFactor(1, 2)
        root.addWidget(body, 1)

    def _connect_signals(self) -> None:
        self.search_edit.textChanged.connect(lambda _text: self.apply_filter())
        self.list_widget.currentRowChanged.connect(lambda _row: self.update_detail())
        self.raw_toggle.toggled.connect(lambda _checked: self.update_detail())
        self.copy_button.clicked.connect(self.copy_current_text)
        self.reinsert_button.clicked.connect(self.reinsert_current_text)
        self.add_dictionary_button.clicked.connect(self.add_selection_to_dictionary)

    def refresh(self) -> None:
        self.rows = self.store.list_recent(limit=self.limit)
        self.apply_filter()

    def apply_filter(self) -> None:
        query = self.search_edit.text().strip().lower()
        if query:
            self.filtered_rows = [row for row in self.rows if self._row_matches(row, query)]
        else:
            self.filtered_rows = list(self.rows)

        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for row in self.filtered_rows:
            self.list_widget.addItem(self._item_text(row))
        self.list_widget.blockSignals(False)

        if self.filtered_rows:
            self.list_widget.setCurrentRow(0)
        else:
            self.detail_editor.clear()
            self.metadata_label.setText("")

    def current_row(self) -> HistoryRow | None:
        index = self.list_widget.currentRow()
        if 0 <= index < len(self.filtered_rows):
            return self.filtered_rows[index]
        return None

    def current_text(self) -> str:
        row = self.current_row()
        if row is None:
            return ""
        return row.raw_text if self.raw_toggle.isChecked() else row.cleaned_text

    def update_detail(self) -> None:
        row = self.current_row()
        if row is None:
            self.detail_editor.clear()
            self.metadata_label.setText("")
            return

        self.detail_editor.setPlainText(self.current_text())
        self.metadata_label.setText(
            " | ".join(
                part
                for part in (
                    row.created_at,
                    row.app_name or "Unknown app",
                    row.mode,
                    row.profile,
                    row.model,
                    self._duration_text(row),
                )
                if part
            )
        )

    def copy_current_text(self) -> bool:
        text = self.current_text()
        if not text:
            return False
        clipboard = self.clipboard or QtWidgets.QApplication.clipboard()
        clipboard.setText(text)
        self.status_label.setText("Copied")
        return True

    def reinsert_current_text(self) -> bool:
        row = self.current_row()
        text = self.current_text()
        if row is None or not text or self.reinsert_callback is None:
            return False
        try:
            self.reinsert_callback(text, row)
        except TypeError:
            self.reinsert_callback(text)
        self.status_label.setText("Queued for insertion")
        return True

    def add_selection_to_dictionary(self) -> str | None:
        selected = self.detail_editor.textCursor().selectedText()
        learned = add_word_to_dictionary_action(
            selected,
            glossary_path=self.glossary_path,
        )
        if learned:
            self.status_label.setText(f"Added {learned}")
        else:
            self.status_label.setText("Select text first")
        return learned

    def _row_matches(self, row: HistoryRow, query: str) -> bool:
        haystack = " ".join(
            str(value or "")
            for value in (
                row.app_name,
                row.raw_text,
                row.cleaned_text,
                row.mode,
                row.profile,
                row.model,
            )
        ).lower()
        return query in haystack

    def _item_text(self, row: HistoryRow) -> str:
        preview = " ".join(row.cleaned_text.split())
        if len(preview) > 80:
            preview = preview[:77] + "..."
        app = row.app_name or "Unknown"
        return f"{preview}  [{app}]"

    def _duration_text(self, row: HistoryRow) -> str:
        if row.duration_seconds is None:
            return ""
        return f"{row.duration_seconds:.1f}s"
