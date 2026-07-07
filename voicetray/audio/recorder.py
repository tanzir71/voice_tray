"""Sounddevice-based push-to-talk audio recorder."""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

LevelCallback = Callable[[float], None]
Clock = Callable[[], float]
StreamFactory = Callable[..., Any]


class NoInputDeviceError(RuntimeError):
    """Raised when no usable input device can be opened."""


class AudioRecorder:
    """Record mono float32 audio into a bounded ring buffer."""

    def __init__(
        self,
        *,
        sample_rate: int = 16_000,
        channels: int = 1,
        max_seconds: float = 600.0,
        level_callback: LevelCallback | None = None,
        level_hz: float = 30.0,
        stream_factory: StreamFactory | None = None,
        clock: Clock = time.monotonic,
        blocksize: int = 0,
        device: int | str | None = None,
    ):
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if channels <= 0:
            raise ValueError("channels must be positive")
        if max_seconds <= 0:
            raise ValueError("max_seconds must be positive")
        if level_hz <= 0:
            raise ValueError("level_hz must be positive")

        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.max_seconds = float(max_seconds)
        self.level_callback = level_callback
        self.level_hz = float(level_hz)
        self.stream_factory = stream_factory or _default_input_stream
        self.clock = clock
        self.blocksize = int(blocksize)
        self.device = device

        self._lock = threading.Lock()
        self._chunks: deque[np.ndarray] = deque()
        self._sample_count = 0
        self._max_samples = max(1, int(round(self.sample_rate * self.max_seconds)))
        self._stream: Any | None = None
        self._recording = False
        self._last_level_emit_at: float | None = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        """Start recording from the configured input stream."""

        with self._lock:
            if self._recording:
                return
            self._chunks.clear()
            self._sample_count = 0
            self._last_level_emit_at = None
            self._recording = True

        try:
            self._stream = self._start_stream_once()
        except Exception as first_error:
            if self.device is None:
                logger.warning("Default input stream failed; retrying once", exc_info=True)
                try:
                    self._stream = self._start_stream_once()
                    return
                except Exception as retry_error:
                    self._reset_after_failed_start()
                    raise NoInputDeviceError("No microphone") from retry_error
            self._reset_after_failed_start()
            raise NoInputDeviceError("No microphone") from first_error

    def stop(self) -> np.ndarray:
        """Stop recording and return captured mono 16 kHz float32 audio."""

        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()

        with self._lock:
            self._recording = False
            if not self._chunks:
                return np.empty(0, dtype=np.float32)
            audio = np.concatenate(list(self._chunks)).astype(np.float32, copy=False)
            self._chunks.clear()
            self._sample_count = 0
            return audio

    def _on_audio(self, indata: Any, _frames: int, _time_info: Any, status: Any) -> None:
        if status:
            logger.debug("Input stream status: %s", status)

        mono = _to_mono_float32(indata)
        if mono.size == 0:
            return

        with self._lock:
            if not self._recording:
                return
            self._append_chunk_locked(mono)

        self._emit_level_if_due(mono)

    def _append_chunk_locked(self, mono: np.ndarray) -> None:
        chunk = np.ascontiguousarray(mono, dtype=np.float32)
        self._chunks.append(chunk)
        self._sample_count += int(chunk.shape[0])

        while self._sample_count > self._max_samples and self._chunks:
            overflow = self._sample_count - self._max_samples
            oldest = self._chunks[0]
            if overflow >= oldest.shape[0]:
                self._chunks.popleft()
                self._sample_count -= int(oldest.shape[0])
                continue
            self._chunks[0] = oldest[overflow:]
            self._sample_count -= overflow

    def _emit_level_if_due(self, mono: np.ndarray) -> None:
        if self.level_callback is None:
            return

        now = self.clock()
        interval = 1.0 / self.level_hz
        if self._last_level_emit_at is not None and now - self._last_level_emit_at < interval:
            return

        self._last_level_emit_at = now
        rms = float(math.sqrt(float(np.mean(np.square(mono, dtype=np.float32)))))
        self.level_callback(rms)

    def _start_stream_once(self) -> Any:
        stream = self.stream_factory(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=self.blocksize,
            device=self.device,
            callback=self._on_audio,
        )
        try:
            stream.start()
        except Exception:
            try:
                stream.close()
            except Exception:
                logger.debug("Could not close failed input stream", exc_info=True)
            raise
        return stream

    def _reset_after_failed_start(self) -> None:
        with self._lock:
            self._recording = False
            self._chunks.clear()
            self._sample_count = 0
        self._stream = None


def _to_mono_float32(indata: Any) -> np.ndarray:
    samples = np.asarray(indata, dtype=np.float32)
    if samples.size == 0:
        return np.empty(0, dtype=np.float32)
    if samples.ndim == 1:
        return samples.astype(np.float32, copy=False)
    if samples.ndim == 2:
        if samples.shape[1] == 1:
            return samples[:, 0].astype(np.float32, copy=False)
        return samples.mean(axis=1, dtype=np.float32).astype(np.float32, copy=False)
    return samples.reshape(samples.shape[0], -1).mean(axis=1, dtype=np.float32)


def _default_input_stream(**kwargs: Any) -> Any:
    import sounddevice as sd

    return sd.InputStream(**kwargs)
