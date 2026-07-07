"""Safe text insertion using clipboard paste with restore."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

FocusProvider = Callable[[], Any]
Sleep = Callable[[float], None]


@dataclass(frozen=True)
class InsertionResult:
    status: str
    method: str
    reason: str = ""


class Inserter:
    """Insert text with clipboard paste by default and per-app typing fallback."""

    def __init__(
        self,
        *,
        clipboard: Any | None = None,
        keyboard: Any | None = None,
        focus_provider: FocusProvider | None = None,
        profiles: list[dict[str, Any]] | None = None,
        sleep: Sleep = time.sleep,
        restore_delay: float = 0.15,
        paste_hotkey: str = "ctrl+v",
    ):
        self.clipboard = clipboard or _PyperclipClipboard()
        self.keyboard = keyboard or _KeyboardAdapter()
        self.focus_provider = focus_provider
        self.profiles = profiles or []
        self.sleep = sleep
        self.restore_delay = float(restore_delay)
        self.paste_hotkey = paste_hotkey

    def insert_text(
        self,
        text: str,
        *,
        start_focus: Any | None = None,
        app_title: str | None = None,
    ) -> InsertionResult:
        if not text:
            return InsertionResult(status="skipped_empty", method="none", reason="empty_text")

        current_focus = self.focus_provider() if self.focus_provider is not None else None
        if start_focus is not None and current_focus is not None and current_focus != start_focus:
            return InsertionResult(
                status="skipped_focus_changed",
                method="none",
                reason="focus_changed",
            )

        method = self._method_for_app(app_title)
        if method == "typing":
            self.keyboard.write(text)
            return InsertionResult(status="inserted", method="typing")

        self._paste_with_restore(text)
        return InsertionResult(status="inserted", method="paste")

    def _paste_with_restore(self, text: str) -> None:
        previous = self.clipboard.paste()
        try:
            self.clipboard.copy(text)
            self.sleep(self.restore_delay)
            self.keyboard.send(self.paste_hotkey)
            self.sleep(self.restore_delay)
        finally:
            self.clipboard.copy(previous)

    def _method_for_app(self, app_title: str | None) -> str:
        if not app_title:
            return "paste"

        lowered_title = app_title.lower()
        for profile in self.profiles:
            match = profile.get("match")
            if not isinstance(match, str) or not match:
                continue
            if match.lower() not in lowered_title:
                continue
            if profile.get("paste_blocked") is True:
                return "typing"
            configured = (
                profile.get("insertion")
                or profile.get("insert_method")
                or profile.get("insertion_method")
            )
            if isinstance(configured, str) and configured.lower() in {"type", "typing"}:
                return "typing"
            if isinstance(configured, str) and configured.lower() == "paste":
                return "paste"
        return "paste"


class _PyperclipClipboard:
    def paste(self) -> str:
        import pyperclip

        value = pyperclip.paste()
        return "" if value is None else str(value)

    def copy(self, text: str) -> None:
        import pyperclip

        pyperclip.copy(text)


class _KeyboardAdapter:
    def send(self, hotkey: str) -> None:
        import keyboard

        keyboard.send(hotkey)

    def write(self, text: str) -> None:
        import keyboard

        keyboard.write(text)
