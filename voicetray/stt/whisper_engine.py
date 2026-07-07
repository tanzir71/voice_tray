"""faster-whisper speech-to-text engine wrapper."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from voicetray.audio.vad import SilenceTrimConfig, trim_silence

logger = logging.getLogger(__name__)

StateCallback = Callable[[str], None]
ModelFactory = Callable[..., Any]


@dataclass(frozen=True)
class WhisperEngineConfig:
    model_size: str = "base"
    language: str = "auto"
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 5
    vad_filter: bool = False
    condition_on_previous_text: bool = False
    local_files_only: bool = True
    silence_trim: bool = True
    silence_padding_ms: int = 120
    vad_aggressiveness: int = 2
    vad_energy_threshold: float = 0.003

    @classmethod
    def from_app_config(cls, config: dict[str, Any]) -> "WhisperEngineConfig":
        stt = config.get("stt", {}) if isinstance(config, dict) else {}
        return cls(
            model_size=str(stt.get("model_size", cls.model_size)),
            language=str(stt.get("language", cls.language)),
            device=str(stt.get("device", cls.device)),
            compute_type=str(stt.get("compute_type", cls.compute_type)),
            local_files_only=bool(stt.get("local_files_only", cls.local_files_only)),
            silence_trim=bool(stt.get("silence_trim", cls.silence_trim)),
            silence_padding_ms=int(stt.get("silence_padding_ms", cls.silence_padding_ms)),
            vad_aggressiveness=int(stt.get("vad_aggressiveness", cls.vad_aggressiveness)),
            vad_energy_threshold=float(
                stt.get("vad_energy_threshold", cls.vad_energy_threshold)
            ),
        )


class WhisperEngine:
    """Lazy faster-whisper wrapper for mono 16 kHz float32 audio."""

    def __init__(
        self,
        config: WhisperEngineConfig | None = None,
        *,
        model_factory: ModelFactory | None = None,
        state_callback: StateCallback | None = None,
    ):
        self.config = config or WhisperEngineConfig()
        self.model_factory = model_factory or _default_model_factory
        self.state_callback = state_callback
        self._model: Any | None = None
        self._model_lock = threading.Lock()
        self.last_timings: dict[str, float] = {"vad": 0.0, "stt": 0.0}

    def transcribe(self, audio: Any) -> str:
        self.last_timings = {"vad": 0.0, "stt": 0.0}
        waveform = _to_mono_float32(audio)
        vad_started = time.perf_counter()
        waveform = self._trim_waveform(waveform)
        self.last_timings["vad"] = time.perf_counter() - vad_started
        if waveform.size == 0:
            return ""

        stt_started = time.perf_counter()
        model = self._load_model()
        self._emit_state("transcribing")
        try:
            segments, _info = model.transcribe(
                waveform,
                beam_size=self.config.beam_size,
                language=_language_arg(self.config.language),
                vad_filter=self.config.vad_filter,
                condition_on_previous_text=self.config.condition_on_previous_text,
            )
            text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
            return " ".join(text.split())
        finally:
            self.last_timings["stt"] = time.perf_counter() - stt_started
            self._emit_state("idle")

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model

        with self._model_lock:
            if self._model is None:
                self._emit_state("loading_model")
                logger.info(
                    "Loading faster-whisper model: size=%s device=%s compute_type=%s",
                    self.config.model_size,
                    self.config.device,
                    self.config.compute_type,
                )
                self._model = self.model_factory(
                    self.config.model_size,
                    device=self.config.device,
                    compute_type=self.config.compute_type,
                    local_files_only=self.config.local_files_only,
                )
            return self._model

    def _emit_state(self, state: str) -> None:
        if self.state_callback:
            self.state_callback(state)

    def _trim_waveform(self, waveform: np.ndarray) -> np.ndarray:
        if not self.config.silence_trim:
            return waveform
        return trim_silence(
            waveform,
            SilenceTrimConfig(
                sample_rate=16_000,
                padding_ms=self.config.silence_padding_ms,
                aggressiveness=self.config.vad_aggressiveness,
                energy_threshold=self.config.vad_energy_threshold,
                enabled=True,
            ),
        )


def _to_mono_float32(audio: Any) -> np.ndarray:
    samples = np.asarray(audio, dtype=np.float32)
    if samples.size == 0:
        return np.empty(0, dtype=np.float32)
    if samples.ndim == 1:
        return np.ascontiguousarray(samples, dtype=np.float32)
    if samples.ndim == 2:
        if samples.shape[1] == 1:
            return np.ascontiguousarray(samples[:, 0], dtype=np.float32)
        return np.ascontiguousarray(samples.mean(axis=1, dtype=np.float32), dtype=np.float32)
    return np.ascontiguousarray(
        samples.reshape(samples.shape[0], -1).mean(axis=1, dtype=np.float32),
        dtype=np.float32,
    )


def _language_arg(language: str) -> str | None:
    value = (language or "").strip().lower()
    return None if value in ("", "auto") else value


def _default_model_factory(*args: Any, **kwargs: Any) -> Any:
    WhisperModel = _import_whisper_model(
        suppress_ipv6_probe=bool(kwargs.get("local_files_only", False))
    )

    return WhisperModel(*args, **kwargs)


def _import_whisper_model(*, suppress_ipv6_probe: bool) -> Any:
    if not suppress_ipv6_probe:
        from faster_whisper import WhisperModel

        return WhisperModel

    import socket

    original_has_ipv6 = socket.has_ipv6
    try:
        # urllib3 probes IPv6 by opening a socket at import time; local dictation forbids that.
        socket.has_ipv6 = False
        from faster_whisper import WhisperModel
    finally:
        socket.has_ipv6 = original_has_ipv6

    return WhisperModel
