import logging
import types

import numpy as np


def test_whisper_engine_records_vad_and_stt_timings():
    from voicetray.stt.whisper_engine import WhisperEngine, WhisperEngineConfig

    class FakeModel:
        def transcribe(self, *_args, **_kwargs):
            return [types.SimpleNamespace(text="hello")], object()

    engine = WhisperEngine(
        WhisperEngineConfig(model_size="base", silence_trim=False),
        model_factory=lambda *_args, **_kwargs: FakeModel(),
    )

    assert engine.transcribe(np.array([0.1, 0.2], dtype=np.float32)) == "hello"

    assert set(engine.last_timings) >= {"vad", "stt"}
    assert engine.last_timings["vad"] >= 0
    assert engine.last_timings["stt"] >= 0


def test_dictation_pipeline_records_rules_and_llm_timings():
    from voicetray.dictation import DictationConfig, DictationContext, DictationPipeline

    class FakeLLM:
        def available(self):
            return False

    pipeline = DictationPipeline(DictationConfig(), llm_cleaner=FakeLLM())

    assert pipeline.process_transcript("um hello hello", DictationContext()) == "Hello"

    assert set(pipeline.last_timings) >= {"rules", "llm"}
    assert pipeline.last_timings["rules"] >= 0
    assert pipeline.last_timings["llm"] >= 0


def test_legacy_process_raw_transcript_logs_per_stage_timings(caplog, monkeypatch):
    from tests.test_legacy_inserter_integration import make_app

    monkeypatch.setattr(logging.getLogger("voicetray"), "propagate", True)
    app = make_app()
    app.performance_clock = iter([10.0, 10.2]).__next__
    app.dictation_pipeline = types.SimpleNamespace(
        process_transcript=lambda raw, context: f"clean {raw}",
        last_timings={"rules": 0.11, "llm": 0.22},
    )
    app.inserter = types.SimpleNamespace(
        insert_text=lambda *_args, **_kwargs: types.SimpleNamespace(status="inserted", method="paste")
    )
    app.history_store = types.SimpleNamespace(append=lambda _entry: 1)

    with caplog.at_level(logging.INFO, logger="voicetray.legacy_app"):
        app.process_raw_transcript(
            "words",
            insert_text=True,
            timings={"record": 1.2, "vad": 0.03, "stt": 0.4},
        )

    assert "Dictation timings:" in caplog.text
    assert "record=1.200s" in caplog.text
    assert "vad=0.030s" in caplog.text
    assert "stt=0.400s" in caplog.text
    assert "rules=0.110s" in caplog.text
    assert "llm=0.220s" in caplog.text
    assert "insert=0.200s" in caplog.text
    assert "total=0.960s" in caplog.text


def test_legacy_small_model_slow_run_suggests_base_model():
    from tests.test_legacy_inserter_integration import make_app

    app = make_app()
    app.stt_config = types.SimpleNamespace(model_size="small")
    app.llm_enabled = False
    notifications = []
    app.show_tray_notification = notifications.append

    app.report_dictation_performance(
        {"record": 10.0, "vad": 0.1, "stt": 1.4, "rules": 0.2, "llm": 0.0, "insert": 0.1}
    )

    assert notifications == [
        "Small model is running slowly; try the base model in Settings > Models."
    ]
