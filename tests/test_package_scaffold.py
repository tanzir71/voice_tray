import importlib
import sys


def test_voicetray_dictation_public_api_processes_transcripts():
    from voicetray.dictation import DictationConfig, DictationContext, process_transcript

    out = process_transcript(
        "hello hello world",
        DictationContext(mode="balanced", profile="general"),
        DictationConfig(glossary_path=""),
    )

    assert "hello world" in out.lower()


def test_legacy_entrypoint_delegates_to_voicetray_main(monkeypatch):
    import voicetray.main as voicetray_main

    calls = []
    monkeypatch.setattr(voicetray_main, "main", lambda: calls.append("called"))
    sys.modules.pop("speech_to_text_app", None)

    legacy_entrypoint = importlib.import_module("speech_to_text_app")
    legacy_entrypoint.main()

    assert calls == ["called"]
