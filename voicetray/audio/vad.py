"""Voice activity detection and leading/trailing silence trimming."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

logger = logging.getLogger(__name__)


class VoiceActivityDetector(Protocol):
    def is_speech(self, frame: bytes, sample_rate: int) -> bool: ...


@dataclass(frozen=True)
class SilenceTrimConfig:
    sample_rate: int = 16_000
    frame_ms: int = 30
    padding_ms: int = 120
    aggressiveness: int = 2
    energy_threshold: float = 0.003
    enabled: bool = True


def trim_silence(
    audio: Any,
    config: SilenceTrimConfig | None = None,
    *,
    vad: VoiceActivityDetector | None = None,
) -> np.ndarray:
    """Return audio bounded by detected speech, or empty for all-silence input."""

    cfg = config or SilenceTrimConfig()
    waveform = _to_mono_float32(audio)
    if waveform.size == 0 or not cfg.enabled:
        return waveform

    _validate_config(cfg)
    frame_samples = int(cfg.sample_rate * cfg.frame_ms / 1000)
    if waveform.size < frame_samples:
        return waveform if _frame_has_energy(waveform, cfg.energy_threshold) else _empty()

    detector = vad if vad is not None else _load_webrtc_vad(cfg.aggressiveness)
    frames = list(_iter_frames(waveform, frame_samples))
    speech_flags = [
        _is_speech(frame, cfg, detector=detector)
        for frame in frames
    ]

    speech_indices = [index for index, is_speech in enumerate(speech_flags) if is_speech]
    if not speech_indices:
        return _empty()

    padding_frames = int(math.ceil(cfg.padding_ms / cfg.frame_ms))
    first = max(0, speech_indices[0] - padding_frames)
    last = min(len(frames) - 1, speech_indices[-1] + padding_frames)
    start_sample = frames[first][0]
    end_sample = frames[last][1]
    return np.ascontiguousarray(waveform[start_sample:end_sample], dtype=np.float32)


def _validate_config(config: SilenceTrimConfig) -> None:
    if config.sample_rate not in (8_000, 16_000, 32_000, 48_000):
        raise ValueError("sample_rate must be one of 8000, 16000, 32000, or 48000")
    if config.frame_ms not in (10, 20, 30):
        raise ValueError("frame_ms must be 10, 20, or 30")
    if config.padding_ms < 0:
        raise ValueError("padding_ms must be non-negative")
    if not 0 <= config.aggressiveness <= 3:
        raise ValueError("aggressiveness must be between 0 and 3")
    if config.energy_threshold < 0:
        raise ValueError("energy_threshold must be non-negative")


def _iter_frames(waveform: np.ndarray, frame_samples: int):
    for start in range(0, waveform.size, frame_samples):
        end = min(start + frame_samples, waveform.size)
        frame = waveform[start:end]
        if frame.size < frame_samples:
            frame = np.pad(frame, (0, frame_samples - frame.size))
        yield start, end, frame


def _is_speech(
    frame_info: tuple[int, int, np.ndarray],
    config: SilenceTrimConfig,
    *,
    detector: VoiceActivityDetector | None,
) -> bool:
    _start, _end, frame = frame_info
    pcm = _float32_to_pcm16(frame)
    if detector is not None:
        try:
            if detector.is_speech(pcm.tobytes(), config.sample_rate):
                return True
        except Exception:
            logger.debug("WebRTC VAD frame check failed; falling back to energy", exc_info=True)
    return _frame_has_energy(frame, config.energy_threshold)


def _frame_has_energy(frame: np.ndarray, threshold: float) -> bool:
    if frame.size == 0:
        return False
    rms = math.sqrt(float(np.mean(np.square(frame, dtype=np.float32))))
    return rms >= threshold


def _float32_to_pcm16(frame: np.ndarray) -> np.ndarray:
    clipped = np.clip(frame, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16)


def _load_webrtc_vad(aggressiveness: int) -> VoiceActivityDetector | None:
    try:
        import webrtcvad
    except ImportError:
        return None
    return webrtcvad.Vad(aggressiveness)


def _to_mono_float32(audio: Any) -> np.ndarray:
    samples = np.asarray(audio, dtype=np.float32)
    if samples.size == 0:
        return _empty()
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


def _empty() -> np.ndarray:
    return np.empty(0, dtype=np.float32)
