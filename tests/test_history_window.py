import json
import os
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from voicetray.ui.history_window import add_word_to_dictionary_action


def qt_modules():
    from PySide6 import QtCore, QtGui, QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return types.SimpleNamespace(QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets)


class FakeClipboard:
    def __init__(self):
        self.texts = []

    def setText(self, text):
        self.texts.append(text)


def build_history(tmp_path):
    from voicetray.history import DictationHistoryStore, HistoryEntry

    store = DictationHistoryStore(tmp_path / "history.db")
    store.append(
        HistoryEntry(
            app_name="Notepad",
            raw_text="um older raw",
            cleaned_text="Older clean.",
            mode="balanced",
            profile="notes",
            duration_seconds=2.0,
            model="base",
        )
    )
    store.append(
        HistoryEntry(
            app_name="Code",
            raw_text="newer raw Qwen Turbo",
            cleaned_text="Newer clean Qwen Turbo.",
            mode="aggressive",
            profile="code/comments",
            duration_seconds=1.2,
            model="small",
        )
    )
    return store


def test_history_add_word_to_dictionary_action_learns_selected_word(tmp_path):
    glossary_path = tmp_path / "glossary.json"

    learned = add_word_to_dictionary_action("  Qwen Turbo  ", glossary_path=glossary_path)

    assert learned == "Qwen Turbo"
    saved = json.loads(glossary_path.read_text(encoding="utf-8"))
    assert saved["user_terms"] == ["Qwen Turbo"]


def test_history_add_word_to_dictionary_action_returns_none_for_blank_selection(tmp_path):
    glossary_path = tmp_path / "glossary.json"

    learned = add_word_to_dictionary_action("   ", glossary_path=glossary_path)

    assert learned is None
    assert not glossary_path.exists()


def test_history_window_loads_reverse_chron_and_toggles_raw_clean(tmp_path):
    from voicetray.ui.history_window import HistoryWindow

    store = build_history(tmp_path)
    window = HistoryWindow(qt_modules=qt_modules(), store=store, glossary_path=tmp_path / "glossary.json")

    assert window.list_widget.count() == 2
    assert "Newer clean" in window.list_widget.item(0).text()
    assert "Older clean" in window.list_widget.item(1).text()
    assert window.detail_editor.toPlainText() == "Newer clean Qwen Turbo."
    assert "Code" in window.metadata_label.text()

    window.raw_toggle.setChecked(True)
    assert window.detail_editor.toPlainText() == "newer raw Qwen Turbo"
    window.raw_toggle.setChecked(False)
    assert window.detail_editor.toPlainText() == "Newer clean Qwen Turbo."


def test_history_window_search_filters_rows(tmp_path):
    from voicetray.ui.history_window import HistoryWindow

    store = build_history(tmp_path)
    window = HistoryWindow(qt_modules=qt_modules(), store=store, glossary_path=tmp_path / "glossary.json")

    window.search_edit.setText("older")

    assert window.list_widget.count() == 1
    assert "Older clean" in window.list_widget.item(0).text()
    assert window.detail_editor.toPlainText() == "Older clean."


def test_history_window_copy_reinsert_and_add_dictionary_actions(tmp_path):
    from voicetray.ui.history_window import HistoryWindow

    store = build_history(tmp_path)
    clipboard = FakeClipboard()
    reinserts = []
    glossary_path = tmp_path / "glossary.json"
    window = HistoryWindow(
        qt_modules=qt_modules(),
        store=store,
        clipboard=clipboard,
        reinsert_callback=lambda text, row: reinserts.append((text, row.id)),
        glossary_path=glossary_path,
    )

    window.copy_current_text()
    window.reinsert_current_text()
    window.detail_editor.selectAll()
    learned = window.add_selection_to_dictionary()

    assert clipboard.texts == ["Newer clean Qwen Turbo."]
    assert reinserts == [("Newer clean Qwen Turbo.", 2)]
    assert learned == "Newer clean Qwen Turbo."
    saved = json.loads(glossary_path.read_text(encoding="utf-8"))
    assert saved["user_terms"] == ["Newer clean Qwen Turbo."]
