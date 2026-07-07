from dataclasses import dataclass
from typing import Optional, Tuple

from dictation.glossary import Glossary
from dictation.llm_local import LocalLLMConfig
from dictation.pipeline import DictationConfig, DictationPipeline
from dictation.types import DictationContext


class FakeLLMUnsafeNumbers:
    def available(self) -> bool:
        return True

    def clean(self, text: str, *, tone_hint: str = "neutral") -> Tuple[Optional[str], str]:
        return text.replace("2", "3"), "ok"


class FakeLLMSafePunct:
    def available(self) -> bool:
        return True

    def clean(self, text: str, *, tone_hint: str = "neutral") -> Tuple[Optional[str], str]:
        return text.strip() + ".", "ok"


class FakeLLMRecordsTone:
    def __init__(self):
        self.calls = []

    def available(self) -> bool:
        return True

    def clean(self, text: str, *, tone_hint: str = "neutral") -> Tuple[Optional[str], str]:
        self.calls.append((text, tone_hint))
        return text, "ok"


def test_glossary_protection_survives_rules():
    cfg = DictationConfig(glossary_path="", llm=LocalLLMConfig(enabled=False))
    p = DictationPipeline(cfg)
    p.glossary = Glossary(protected_terms=("ACME-123",), user_terms=(), replacements=())
    out = p.process_transcript("acme-123 is ready", DictationContext(mode="balanced", profile="general"))
    assert "acme-123" in out.lower()


def test_fallback_when_llm_output_is_unsafe():
    cfg = DictationConfig(glossary_path="", llm=LocalLLMConfig(enabled=True, model_path="x"))
    p = DictationPipeline(cfg, llm_cleaner=FakeLLMUnsafeNumbers())
    out = p.process_transcript("send 2 files", DictationContext(mode="balanced", profile="general"))
    assert "2" in out
    assert "3" not in out


def test_mode_differences_raw_vs_balanced_vs_aggressive():
    cfg = DictationConfig(glossary_path="", llm=LocalLLMConfig(enabled=False))
    p = DictationPipeline(cfg)
    raw = p.process_transcript("um like hello hello world", DictationContext(mode="raw", profile="general"))
    balanced = p.process_transcript("um like hello hello world", DictationContext(mode="balanced", profile="general"))
    aggressive = p.process_transcript("um like hello hello world", DictationContext(mode="aggressive", profile="general"))

    assert raw.lower().startswith("um")
    assert balanced.startswith("Like")
    assert "like hello world" in balanced.lower()
    assert "um" not in balanced.lower()
    assert "um" not in aggressive.lower()
    assert "like" not in aggressive.lower()


def test_llm_safe_output_is_accepted():
    cfg = DictationConfig(glossary_path="", llm=LocalLLMConfig(enabled=True, model_path="x"))
    p = DictationPipeline(cfg, llm_cleaner=FakeLLMSafePunct())
    out = p.process_transcript("hello world", DictationContext(mode="balanced", profile="general"))
    assert out.endswith(".")


def test_notes_and_email_profiles_auto_structure_numbered_lists():
    cfg = DictationConfig(glossary_path="", llm=LocalLLMConfig(enabled=False))
    p = DictationPipeline(cfg)

    for profile in ("notes", "email"):
        out = p.process_transcript(
            "one apples two bananas three carrots",
            DictationContext(mode="balanced", profile=profile),
        )
        assert out == "1. Apples\n2. Bananas\n3. Carrots"


def test_general_profile_does_not_auto_structure_enumerations():
    cfg = DictationConfig(glossary_path="", llm=LocalLLMConfig(enabled=False))
    p = DictationPipeline(cfg)

    out = p.process_transcript(
        "one apples two bananas three carrots",
        DictationContext(mode="balanced", profile="general"),
    )

    assert "\n" not in out
    assert not out.startswith("1.")


def test_notes_and_email_profiles_convert_new_paragraph():
    cfg = DictationConfig(glossary_path="", llm=LocalLLMConfig(enabled=False))
    p = DictationPipeline(cfg)

    for profile in ("notes", "email"):
        out = p.process_transcript(
            "opening thought new paragraph next thought",
            DictationContext(mode="balanced", profile=profile),
        )
        expected = "Opening thought\n\nNext thought."
        if profile == "notes":
            expected = "Opening thought\n\nNext thought"
        assert out == expected


def test_general_profile_keeps_new_paragraph_as_words():
    cfg = DictationConfig(glossary_path="", llm=LocalLLMConfig(enabled=False))
    p = DictationPipeline(cfg)

    out = p.process_transcript(
        "opening thought new paragraph next thought",
        DictationContext(mode="balanced", profile="general"),
    )

    assert "\n" not in out
    assert "new paragraph" in out.lower()


def test_pipeline_passes_profile_tone_hint_to_llm():
    cfg = DictationConfig(glossary_path="", llm=LocalLLMConfig(enabled=True, model_path="x"))

    expected_tones = {
        "email": "formal",
        "chat": "casual",
        "notes": "terse",
        "general": "neutral",
    }
    for profile, expected_tone in expected_tones.items():
        fake_llm = FakeLLMRecordsTone()
        p = DictationPipeline(cfg, llm_cleaner=fake_llm)

        p.process_transcript("hello world", DictationContext(mode="balanced", profile=profile))

        assert fake_llm.calls
        assert fake_llm.calls[0][1] == expected_tone


def test_pipeline_learn_word_persists_and_reloads_glossary(tmp_path):
    glossary_path = tmp_path / "glossary.json"
    cfg = DictationConfig(glossary_path=str(glossary_path), llm=LocalLLMConfig(enabled=False))
    p = DictationPipeline(cfg)

    glossary = p.learn_word("Qwen Turbo")

    assert glossary.user_terms == ("Qwen Turbo",)
    assert p.glossary.user_terms == ("Qwen Turbo",)
    out = p.process_transcript("qwen turbo is ready", DictationContext(mode="balanced", profile="general"))
    assert "qwen turbo" in out.lower()

