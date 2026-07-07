"""Global hold-to-record hotkey controller."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

Clock = Callable[[], float]
StartCallback = Callable[[], None]
StopCallback = Callable[["RecordingSession"], None]


@dataclass(frozen=True)
class HotkeyConfig:
    record_hotkey: str = "f9"
    alternate_record_hotkey: str | None = "ctrl+win"
    cancel_hotkey: str = "esc"
    tap_lock_ms: int = 300
    suppress: bool = False
    timeout: float = 1.0

    @classmethod
    def from_app_config(cls, config: dict[str, Any]) -> "HotkeyConfig":
        hotkeys = config.get("hotkeys", {}) if isinstance(config, dict) else {}
        return cls(
            record_hotkey=str(hotkeys.get("speech", cls.record_hotkey)),
            alternate_record_hotkey=str(
                hotkeys.get("speech_alternative", cls.alternate_record_hotkey)
            ),
            cancel_hotkey=str(hotkeys.get("cancel", cls.cancel_hotkey)),
            tap_lock_ms=int(hotkeys.get("tap_lock_ms", cls.tap_lock_ms)),
        )


@dataclass(frozen=True)
class RecordingSession:
    started_at: float
    stopped_at: float
    locked: bool

    @property
    def duration_seconds(self) -> float:
        return self.stopped_at - self.started_at


class HotkeyController:
    """State machine for hold-to-talk plus short-tap lock mode."""

    def __init__(
        self,
        config: HotkeyConfig | None = None,
        *,
        on_record_start: StartCallback,
        on_record_stop: StopCallback,
        clock: Clock = time.monotonic,
    ):
        self.config = config or HotkeyConfig()
        self.on_record_start = on_record_start
        self.on_record_stop = on_record_stop
        self.clock = clock

        self._lock = threading.RLock()
        self._keyboard: Any | None = None
        self._handles: list[Any] = []
        self._pressed_hotkey: str | None = None
        self._pressed_at: float | None = None
        self._recording_started_at: float | None = None
        self._locked = False
        self._listening = False

    @property
    def is_listening(self) -> bool:
        return self._listening

    @property
    def is_recording(self) -> bool:
        return self._recording_started_at is not None

    @property
    def is_locked(self) -> bool:
        return self._locked

    def is_backend_alive(self) -> bool:
        with self._lock:
            if not self._listening or self._keyboard is None:
                return False
            keyboard_module = self._keyboard

        listener = getattr(keyboard_module, "_listener", None)
        if listener is None:
            return True
        thread = getattr(listener, "thread", None)
        if thread is not None and hasattr(thread, "is_alive"):
            try:
                return bool(thread.is_alive())
            except Exception:
                logger.debug("Could not inspect keyboard listener thread", exc_info=True)
        if hasattr(listener, "is_alive"):
            try:
                return bool(listener.is_alive())
            except Exception:
                logger.debug("Could not inspect keyboard listener", exc_info=True)
        if hasattr(listener, "listening"):
            return bool(getattr(listener, "listening"))
        return True

    def restart_if_dead(self) -> bool:
        with self._lock:
            if not self._listening or self._keyboard is None:
                return False
            keyboard_module = self._keyboard

        if self.is_backend_alive():
            return False

        logger.warning("Keyboard listener appears dead; restarting hotkeys")
        self.stop()
        self.start(keyboard_module)
        return True

    def start(self, keyboard_module: Any | None = None) -> None:
        with self._lock:
            if self._listening:
                return
            self._keyboard = keyboard_module or _import_keyboard()
            self._handles = []

            for hotkey in self._record_hotkeys():
                self._handles.append(
                    self._keyboard.add_hotkey(
                        hotkey,
                        lambda hotkey=hotkey: self._on_record_press(hotkey),
                        suppress=self.config.suppress,
                        timeout=self.config.timeout,
                    )
                )
                self._handles.append(
                    self._keyboard.add_hotkey(
                        hotkey,
                        lambda hotkey=hotkey: self._on_record_release(hotkey),
                        suppress=self.config.suppress,
                        timeout=self.config.timeout,
                        trigger_on_release=True,
                    )
                )

            if self.config.cancel_hotkey:
                self._handles.append(
                    self._keyboard.add_hotkey(
                        self.config.cancel_hotkey,
                        self._on_cancel_press,
                        suppress=self.config.suppress,
                        timeout=self.config.timeout,
                    )
                )
            self._listening = True

    def stop(self) -> None:
        with self._lock:
            handles = list(self._handles)
            keyboard_module = self._keyboard
            self._handles.clear()
            self._keyboard = None
            self._listening = False
            self._pressed_hotkey = None
            self._pressed_at = None
            self._locked = False
            self._recording_started_at = None

        if keyboard_module is not None:
            for handle in handles:
                try:
                    keyboard_module.remove_hotkey(handle)
                except Exception:
                    logger.debug("Could not remove hotkey handle %r", handle, exc_info=True)

    def force_stop(self) -> RecordingSession | None:
        """Stop the active recording from an external timeout or UI control."""
        session: RecordingSession | None = None
        with self._lock:
            if self.is_recording:
                session = self._finish_recording_locked(self.clock(), locked=self._locked)

        if session is not None:
            self.on_record_stop(session)
        return session

    def _record_hotkeys(self) -> list[str]:
        hotkeys = [self.config.record_hotkey, self.config.alternate_record_hotkey]
        seen = set()
        normalized = []
        for hotkey in hotkeys:
            value = (hotkey or "").strip()
            if value and value not in seen:
                normalized.append(value)
                seen.add(value)
        return normalized

    def _on_record_press(self, hotkey: str) -> None:
        with self._lock:
            if self._locked:
                self._pressed_hotkey = hotkey
                self._pressed_at = self.clock()
                return
            if self.is_recording:
                return
            now = self.clock()
            self._pressed_hotkey = hotkey
            self._pressed_at = now
            self._recording_started_at = now

        self.on_record_start()

    def _on_record_release(self, hotkey: str) -> None:
        session: RecordingSession | None = None
        with self._lock:
            if self._pressed_hotkey != hotkey or self._pressed_at is None:
                return
            now = self.clock()
            press_duration = now - self._pressed_at
            tap_threshold = self.config.tap_lock_ms / 1000.0

            if self._locked:
                session = self._finish_recording_locked(now, locked=True)
            elif press_duration < tap_threshold:
                self._locked = True
                self._pressed_hotkey = None
                self._pressed_at = None
            else:
                session = self._finish_recording_locked(now, locked=False)

        if session is not None:
            self.on_record_stop(session)

    def _on_cancel_press(self) -> None:
        session: RecordingSession | None = None
        with self._lock:
            if self.is_recording:
                session = self._finish_recording_locked(self.clock(), locked=self._locked)

        if session is not None:
            self.on_record_stop(session)

    def _finish_recording_locked(self, stopped_at: float, *, locked: bool) -> RecordingSession | None:
        if self._recording_started_at is None:
            return None
        session = RecordingSession(
            started_at=self._recording_started_at,
            stopped_at=stopped_at,
            locked=locked,
        )
        self._pressed_hotkey = None
        self._pressed_at = None
        self._recording_started_at = None
        self._locked = False
        return session


def _import_keyboard() -> Any:
    import keyboard

    return keyboard
