import math
import wave

import numpy as np


def test_trim_silence_removes_leading_and_trailing_quiet_audio():
    from voicetray.audio.vad import SilenceTrimConfig, trim_silence

    sample_rate = 16_000
    leading = np.zeros(sample_rate // 2, dtype=np.float32)
    speech = 0.2 * np.sin(np.linspace(0, 2 * math.pi * 12, sample_rate, dtype=np.float32))
    trailing = np.zeros(sample_rate // 2, dtype=np.float32)
    audio = np.concatenate([leading, speech, trailing])

    trimmed = trim_silence(
        audio,
        SilenceTrimConfig(sample_rate=sample_rate, padding_ms=0, energy_threshold=0.01),
    )

    assert 0 < trimmed.size < audio.size
    assert np.max(np.abs(trimmed[:sample_rate // 10])) > 0.01
    assert np.max(np.abs(trimmed[-sample_rate // 10:])) > 0.01


def test_trim_silence_returns_empty_for_all_silence():
    from voicetray.audio.vad import SilenceTrimConfig, trim_silence

    trimmed = trim_silence(
        np.zeros(16_000, dtype=np.float32),
        SilenceTrimConfig(sample_rate=16_000),
    )

    assert trimmed.size == 0
    assert trimmed.dtype == np.float32


def test_trim_silence_uses_webrtc_vad_frames_when_available():
    from voicetray.audio.vad import SilenceTrimConfig, trim_silence

    class FakeVad:
        def __init__(self):
            self.calls = []
            self.flags = [False, True, True, False]

        def is_speech(self, frame, sample_rate):
            self.calls.append((frame, sample_rate))
            return self.flags[len(self.calls) - 1]

    sample_rate = 16_000
    frame_samples = int(sample_rate * 0.03)
    audio = np.concatenate(
        [
            np.zeros(frame_samples, dtype=np.float32),
            np.full(frame_samples * 2, 0.1, dtype=np.float32),
            np.zeros(frame_samples, dtype=np.float32),
        ]
    )
    vad = FakeVad()

    trimmed = trim_silence(
        audio,
        SilenceTrimConfig(
            sample_rate=sample_rate,
            frame_ms=30,
            padding_ms=0,
            energy_threshold=1.0,
        ),
        vad=vad,
    )

    assert trimmed.size == frame_samples * 2
    assert all(sample_rate == call_sample_rate for _frame, call_sample_rate in vad.calls)
    assert all(len(frame) == frame_samples * 2 for frame, _sample_rate in vad.calls)


def test_silent_wav_transcription_returns_empty_without_loading_model(tmp_path):
    from voicetray.stt.whisper_engine import WhisperEngine, WhisperEngineConfig

    wav_path = tmp_path / "silence.wav"
    samples = np.zeros(16_000, dtype=np.int16)
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(samples.tobytes())

    with wave.open(str(wav_path), "rb") as wav:
        audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16).astype(np.float32)
        audio /= 32768.0

    def factory(*_args, **_kwargs):
        raise AssertionError("model should not load for a silent utterance")

    engine = WhisperEngine(WhisperEngineConfig(), model_factory=factory)

    assert engine.transcribe(audio) == ""
