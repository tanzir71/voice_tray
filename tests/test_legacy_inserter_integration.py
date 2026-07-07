import types


def make_app():
    from voicetray.legacy_app import VoiceTrayApp

    app = VoiceTrayApp.__new__(VoiceTrayApp)
    app.last_recognized_text = ""
    app.recording_focus_token = "start-hwnd"
    app.selected_context = types.SimpleNamespace(mode="balanced", profile="notes")
    app.select_dictation_context = lambda: app.selected_context
    app.dictation_pipeline = types.SimpleNamespace(
        process_transcript=lambda raw, context: f"clean {raw}"
    )
    app.expand_snippets = lambda text: text
    app.check_similarity_with_recent = lambda raw: False
    app.recent_texts = []
    app.max_recent_texts = 5
    app.stt_config = types.SimpleNamespace(model_size="base")
    app.get_active_window_title = lambda: "Notepad"
    return app


def test_legacy_process_raw_transcript_uses_inserter_for_text_insertion():
    app = make_app()
    events = []
    app.inserter = types.SimpleNamespace(
        insert_text=lambda text, **kwargs: events.append(("insert", text, kwargs))
        or types.SimpleNamespace(status="inserted", method="paste")
    )
    app.history_store = types.SimpleNamespace(
        append=lambda entry: events.append(("history", entry)) or 1
    )

    assert app.process_raw_transcript("words", insert_text=True) == "clean words"

    assert events[0][0] == "history"
    history_entry = events[0][1]
    assert history_entry.app_name == "Notepad"
    assert history_entry.raw_text == "words"
    assert history_entry.cleaned_text == "clean words"
    assert history_entry.mode == "balanced"
    assert history_entry.profile == "notes"
    assert history_entry.duration_seconds is None
    assert history_entry.model == "base"
    assert events[1] == (
        "insert",
        "clean words",
        {"start_focus": "start-hwnd", "app_title": "Notepad"},
    )
    assert app.last_recognized_text == "clean words"


def test_legacy_process_raw_transcript_records_history_before_insertion():
    app = make_app()
    events = []

    def insert_text(_text, **_kwargs):
        events.append("insert")
        return types.SimpleNamespace(status="inserted", method="paste")

    def append_history(_entry):
        events.append("history")
        return 1

    app.inserter = types.SimpleNamespace(insert_text=insert_text)
    app.history_store = types.SimpleNamespace(append=append_history)

    app.process_raw_transcript("words", insert_text=True)

    assert events == ["history", "insert"]


def test_legacy_process_raw_transcript_uses_supplied_duration():
    app = make_app()
    entries = []
    app.inserter = types.SimpleNamespace(
        insert_text=lambda *_args, **_kwargs: types.SimpleNamespace(status="inserted", method="paste")
    )
    app.history_store = types.SimpleNamespace(append=lambda entry: entries.append(entry) or 1)

    app.process_raw_transcript("words", insert_text=True, duration_seconds=3.25)

    assert entries[0].duration_seconds == 3.25


def test_legacy_process_raw_transcript_without_insertion_still_records_history():
    app = make_app()
    entries = []
    insert_calls = []
    app.inserter = types.SimpleNamespace(
        insert_text=lambda *_args, **_kwargs: insert_calls.append("insert")
    )
    app.history_store = types.SimpleNamespace(append=lambda entry: entries.append(entry) or 1)

    app.process_raw_transcript("words", insert_text=False)

    assert len(entries) == 1
    assert insert_calls == []


def test_legacy_focus_change_relies_on_sqlite_history_and_notifies():
    app = make_app()
    notifications = []
    app.show_tray_notification = notifications.append
    history_entries = []
    app.history_store = types.SimpleNamespace(append=lambda entry: history_entries.append(entry) or 1)
    app.inserter = types.SimpleNamespace(
        insert_text=lambda *_args, **_kwargs: types.SimpleNamespace(
            status="skipped_focus_changed",
            method="none",
        )
    )

    assert app.process_raw_transcript("words", insert_text=True) == "clean words"

    assert len(history_entries) == 1
    assert history_entries[0].cleaned_text == "clean words"
    assert notifications == ["Copied to history; focus changed before insertion."]


def test_legacy_init_history_store_creates_store_with_default_path(monkeypatch):
    import voicetray.legacy_app as legacy_app

    created = []

    class FakeStore:
        def __init__(self, path=None):
            created.append(path)

    monkeypatch.setattr(legacy_app, "DictationHistoryStore", FakeStore)
    app = make_app()

    app.init_history_store()

    assert isinstance(app.history_store, FakeStore)
    assert created == [None]
