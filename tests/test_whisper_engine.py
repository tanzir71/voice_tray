import os
import builtins
import types
import wave

import numpy as np
import pytest


class FakeWhisperModel:
    instances = []

    def __init__(self, segments):
        self.segments = segments
        self.calls = []
        FakeWhisperModel.instances.append(self)

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        return (iter(self.segments), types.SimpleNamespace(language="en"))


def test_whisper_engine_lazy_loads_model_and_joins_segments():
    from voicetray.stt.whisper_engine import WhisperEngine, WhisperEngineConfig

    created = []
    states = []

    def factory(*args, **kwargs):
        created.append((args, kwargs))
        return FakeWhisperModel(
            [
                types.SimpleNamespace(text=" hello"),
                types.SimpleNamespace(text=" world "),
            ]
        )

    engine = WhisperEngine(
        WhisperEngineConfig(model_size="small", language="en", device="cpu", compute_type="int8"),
        model_factory=factory,
        state_callback=states.append,
    )

    assert created == []

    text = engine.transcribe(np.array([0.0, 0.1], dtype=np.float32))

    assert text == "hello world"
    assert created == [
        (
            ("small",),
            {"device": "cpu", "compute_type": "int8", "local_files_only": True},
        )
    ]
    assert FakeWhisperModel.instances[-1].calls[0][1] == {
        "beam_size": 5,
        "language": "en",
        "vad_filter": False,
        "condition_on_previous_text": False,
    }
    assert states == ["loading_model", "transcribing", "idle"]


def test_whisper_engine_reuses_loaded_model_and_auto_language_passes_none():
    from voicetray.stt.whisper_engine import WhisperEngine, WhisperEngineConfig

    created = []

    def factory(*args, **kwargs):
        created.append((args, kwargs))
        return FakeWhisperModel([types.SimpleNamespace(text="once")])

    engine = WhisperEngine(
        WhisperEngineConfig(model_size="base", language="auto"),
        model_factory=factory,
    )

    assert engine.transcribe(np.array([0.1], dtype=np.float32)) == "once"
    assert engine.transcribe(np.array([0.2], dtype=np.float32)) == "once"

    assert len(created) == 1
    assert FakeWhisperModel.instances[-1].calls[-1][1]["language"] is None


def test_whisper_engine_trims_silence_before_transcribing():
    from voicetray.stt.whisper_engine import WhisperEngine, WhisperEngineConfig

    sample_rate = 16_000
    leading = np.zeros(sample_rate // 2, dtype=np.float32)
    speech = np.full(sample_rate // 2, 0.1, dtype=np.float32)
    trailing = np.zeros(sample_rate // 2, dtype=np.float32)
    audio = np.concatenate([leading, speech, trailing])

    def factory(*_args, **_kwargs):
        return FakeWhisperModel([types.SimpleNamespace(text="trimmed")])

    engine = WhisperEngine(
        WhisperEngineConfig(silence_padding_ms=0, vad_energy_threshold=0.01),
        model_factory=factory,
    )

    assert engine.transcribe(audio) == "trimmed"
    sent_audio = FakeWhisperModel.instances[-1].calls[-1][0]
    assert 0 < sent_audio.size < audio.size
    assert np.max(np.abs(sent_audio[:sample_rate // 10])) > 0.01
    assert np.max(np.abs(sent_audio[-sample_rate // 10:])) > 0.01


def test_whisper_engine_from_app_config_uses_stt_settings():
    from voicetray.config import default_config
    from voicetray.stt.whisper_engine import WhisperEngineConfig

    cfg = default_config()
    cfg["stt"].update(
        {
            "model_size": "medium",
            "language": "en",
            "device": "cuda",
            "compute_type": "float16",
            "silence_trim": False,
            "silence_padding_ms": 90,
            "vad_aggressiveness": 3,
            "vad_energy_threshold": 0.02,
        }
    )

    engine_cfg = WhisperEngineConfig.from_app_config(cfg)

    assert engine_cfg.model_size == "medium"
    assert engine_cfg.language == "en"
    assert engine_cfg.device == "cuda"
    assert engine_cfg.compute_type == "float16"
    assert engine_cfg.silence_trim is False
    assert engine_cfg.silence_padding_ms == 90
    assert engine_cfg.vad_aggressiveness == 3
    assert engine_cfg.vad_energy_threshold == 0.02


def test_whisper_engine_empty_audio_returns_empty_without_loading_model():
    from voicetray.stt.whisper_engine import WhisperEngine, WhisperEngineConfig

    def factory(*_args, **_kwargs):
        raise AssertionError("model should not be loaded for empty audio")

    engine = WhisperEngine(WhisperEngineConfig(), model_factory=factory)

    assert engine.transcribe(np.array([], dtype=np.float32)) == ""


def test_default_model_factory_suppresses_ipv6_probe_for_local_only_import(monkeypatch):
    import socket

    import voicetray.stt.whisper_engine as whisper_engine

    original_import = builtins.__import__
    observed_has_ipv6 = []

    class FakeModel:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "faster_whisper":
            observed_has_ipv6.append(socket.has_ipv6)
            return types.SimpleNamespace(WhisperModel=FakeModel)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(socket, "has_ipv6", True)

    model = whisper_engine._default_model_factory("tiny", local_files_only=True)

    assert observed_has_ipv6 == [False]
    assert socket.has_ipv6 is True
    assert model.args == ("tiny",)
    assert model.kwargs == {"local_files_only": True}


def test_hello_wav_fixture_is_three_second_mono_16khz():
    fixture = "tests/fixtures/hello.wav"

    with wave.open(fixture, "rb") as wav:
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getnframes() == 48000


@pytest.mark.integration
def test_whisper_engine_transcribes_hello_wav_fixture_when_enabled():
    if os.environ.get("VOICETRAY_RUN_WHISPER_INTEGRATION") != "1":
        pytest.skip("Set VOICETRAY_RUN_WHISPER_INTEGRATION=1 to run faster-whisper model test")

    pytest.importorskip("faster_whisper")
    sf = pytest.importorskip("soundfile")
    from voicetray.stt.whisper_engine import WhisperEngine, WhisperEngineConfig

    audio, sample_rate = sf.read("tests/fixtures/hello.wav", dtype="float32")
    assert sample_rate == 16000

    engine = WhisperEngine(
        WhisperEngineConfig(
            model_size=os.environ.get("VOICETRAY_TEST_WHISPER_MODEL", "tiny"),
            language="en",
            device="cpu",
            compute_type="int8",
            local_files_only=False,
        )
    )

    assert engine.transcribe(audio).strip()
