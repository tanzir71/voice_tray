from dataclasses import dataclass
from typing import Optional, Tuple

from dictation.glossary import Glossary
from dictation.llm_local import LocalLLMConfig
from dictation.pipeline import DictationConfig, DictationPipeline
from dictation.types import DictationContext


class FakeLLMUnsafeNumbers:
    def available(self) -> bool:
        return True

    def clean(self, text: str) -> Tuple[Optional[str], str]:
        return text.replace("2", "3"), "ok"


class FakeLLMSafePunct:
    def available(self) -> bool:
        return True

    def clean(self, text: str) -> Tuple[Optional[str], str]:
        return text.strip() + ".", "ok"


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
    raw = p.process_transcript("um hello hello world", DictationContext(mode="raw", profile="general"))
    balanced = p.process_transcript("um hello hello world", DictationContext(mode="balanced", profile="general"))
    aggressive = p.process_transcript("um hello hello world", DictationContext(mode="aggressive", profile="general"))

    assert raw.lower().startswith("um")
    assert balanced.startswith("Um")
    assert "hello world" in balanced.lower()
    assert "um" in balanced.lower()
    assert "um" not in aggressive.lower()


def test_llm_safe_output_is_accepted():
    cfg = DictationConfig(glossary_path="", llm=LocalLLMConfig(enabled=True, model_path="x"))
    p = DictationPipeline(cfg, llm_cleaner=FakeLLMSafePunct())
    out = p.process_transcript("hello world", DictationContext(mode="balanced", profile="general"))
    assert out.endswith(".")

