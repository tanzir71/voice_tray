import pytest
from pathlib import Path


class FakeClipboard:
    def __init__(self, initial="original"):
        self.value = initial
        self.ops = []

    def paste(self):
        self.ops.append(("paste", self.value))
        return self.value

    def copy(self, text):
        self.ops.append(("copy", text))
        self.value = text


class FakeKeyboard:
    def __init__(self):
        self.ops = []

    def send(self, hotkey):
        self.ops.append(("send", hotkey))

    def write(self, text):
        self.ops.append(("write", text))


def test_clipboard_paste_insertion_saves_and_restores_clipboard():
    from voicetray.insert.inserter import Inserter

    clipboard = FakeClipboard("before")
    keyboard = FakeKeyboard()
    sleeps = []

    inserter = Inserter(
        clipboard=clipboard,
        keyboard=keyboard,
        sleep=sleeps.append,
        restore_delay=0.15,
        focus_provider=lambda: "notepad-hwnd",
    )

    result = inserter.insert_text("hello world", start_focus="notepad-hwnd", app_title="Notepad")

    assert result.status == "inserted"
    assert result.method == "paste"
    assert clipboard.ops == [
        ("paste", "before"),
        ("copy", "hello world"),
        ("copy", "before"),
    ]
    assert keyboard.ops == [("send", "ctrl+v")]
    assert sleeps == [0.15, 0.15]
    assert clipboard.value == "before"


def test_clipboard_is_restored_if_paste_hotkey_fails():
    from voicetray.insert.inserter import Inserter

    class FailingKeyboard(FakeKeyboard):
        def send(self, hotkey):
            super().send(hotkey)
            raise RuntimeError("paste failed")

    clipboard = FakeClipboard("before")
    keyboard = FailingKeyboard()
    inserter = Inserter(
        clipboard=clipboard,
        keyboard=keyboard,
        sleep=lambda _seconds: None,
        focus_provider=lambda: "same",
    )

    with pytest.raises(RuntimeError, match="paste failed"):
        inserter.insert_text("hello", start_focus="same")

    assert clipboard.value == "before"
    assert clipboard.ops[-1] == ("copy", "before")


def test_focus_change_skips_insertion_without_touching_clipboard_or_keyboard():
    from voicetray.insert.inserter import Inserter

    clipboard = FakeClipboard("before")
    keyboard = FakeKeyboard()
    inserter = Inserter(
        clipboard=clipboard,
        keyboard=keyboard,
        focus_provider=lambda: "browser-hwnd",
    )

    result = inserter.insert_text("do not insert", start_focus="editor-hwnd")

    assert result.status == "skipped_focus_changed"
    assert result.method == "none"
    assert clipboard.ops == []
    assert keyboard.ops == []


def test_app_profile_can_force_typing_fallback_for_paste_blocked_apps():
    from voicetray.insert.inserter import Inserter

    clipboard = FakeClipboard("before")
    keyboard = FakeKeyboard()
    inserter = Inserter(
        clipboard=clipboard,
        keyboard=keyboard,
        profiles=[{"match": "terminal", "insertion": "typing"}],
        focus_provider=lambda: "terminal-hwnd",
    )

    result = inserter.insert_text("typed text", start_focus="terminal-hwnd", app_title="Windows Terminal")

    assert result.status == "inserted"
    assert result.method == "typing"
    assert keyboard.ops == [("write", "typed text")]
    assert clipboard.ops == []


def test_paste_blocked_profile_alias_uses_typing_fallback():
    from voicetray.insert.inserter import Inserter

    keyboard = FakeKeyboard()
    inserter = Inserter(
        clipboard=FakeClipboard("before"),
        keyboard=keyboard,
        profiles=[{"match": "legacy app", "paste_blocked": True}],
        focus_provider=lambda: "legacy-hwnd",
    )

    result = inserter.insert_text("typed text", start_focus="legacy-hwnd", app_title="Legacy App")

    assert result.method == "typing"
    assert keyboard.ops == [("write", "typed text")]


def test_character_typing_dependency_is_removed_from_runtime_sources():
    root = Path(__file__).resolve().parents[1]
    forbidden = "py" "autogui"
    paths = [
        root / "requirements.txt",
        root / "readme.md",
        *list((root / "voicetray").rglob("*.py")),
    ]

    hits = [
        str(path.relative_to(root))
        for path in paths
        if forbidden in path.read_text(encoding="utf-8", errors="ignore").lower()
    ]

    assert hits == []
