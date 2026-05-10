from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .glossary import Glossary, apply_replacements, load_glossary, protect_terms, restore_terms
from .llm_local import LocalLLMConfig, LocalLLMCleaner
from .protect import protect_spans, restore_spans
from .rules import RuleOptions, apply_rules
from .types import DictationContext
from .validation import ValidationResult, validate_llm_output


@dataclass(frozen=True)
class DictationConfig:
    glossary_path: str = ""
    llm: LocalLLMConfig = LocalLLMConfig()


def _options_for(context: DictationContext) -> RuleOptions:
    if context.profile == "code/comments":
        return RuleOptions(
            remove_fillers=False,
            remove_repetitions=True,
            handle_self_corrections=False,
            normalize_punctuation=False,
            normalize_capitalization=False,
            normalize_whitespace=True,
            enable_list_formatting=False,
            convert_spoken_punctuation=False,
            convert_spoken_newlines=False,
            final_period=False,
        )

    if context.mode == "raw":
        return RuleOptions(
            remove_fillers=False,
            remove_repetitions=False,
            handle_self_corrections=False,
            normalize_punctuation=False,
            normalize_capitalization=False,
            normalize_whitespace=True,
            enable_list_formatting=False,
            convert_spoken_punctuation=False,
            convert_spoken_newlines=False,
            final_period=False,
        )

    enable_list = context.profile in ("notes",)
    newlines = context.profile in ("notes", "email")
    final_period = context.profile in ("email",)

    if context.mode == "aggressive":
        return RuleOptions(
            remove_fillers=True,
            aggressive_fillers=True,
            remove_repetitions=True,
            handle_self_corrections=True,
            normalize_punctuation=True,
            normalize_capitalization=True,
            normalize_whitespace=True,
            enable_list_formatting=enable_list,
            convert_spoken_punctuation=True,
            convert_spoken_newlines=newlines,
            final_period=final_period,
        )

    return RuleOptions(
        remove_fillers=False,
        aggressive_fillers=False,
        remove_repetitions=True,
        handle_self_corrections=False,
        normalize_punctuation=True,
        normalize_capitalization=True,
        normalize_whitespace=True,
        enable_list_formatting=enable_list,
        convert_spoken_punctuation=False,
        convert_spoken_newlines=newlines,
        final_period=final_period,
    )


class DictationPipeline:
    def __init__(self, cfg: DictationConfig, llm_cleaner: Optional[LocalLLMCleaner] = None):
        self.cfg = cfg
        self.glossary: Glossary = load_glossary(cfg.glossary_path) if cfg.glossary_path else Glossary()
        self.llm = llm_cleaner if llm_cleaner is not None else LocalLLMCleaner(cfg.llm)

    def reload_glossary(self):
        self.glossary = load_glossary(self.cfg.glossary_path) if self.cfg.glossary_path else Glossary()

    def process_transcript(self, raw_text: str, context: DictationContext) -> str:
        if not raw_text:
            return ""

        text = raw_text
        text = apply_replacements(text, self.glossary)
        protected_text, mapping = protect_terms(text, self.glossary)
        protected_text, span_mapping = protect_spans(protected_text)

        rule_opts = _options_for(context)
        rule_clean = apply_rules(protected_text, rule_opts)

        if context.mode == "raw" or context.profile == "code/comments":
            out = restore_spans(rule_clean, span_mapping)
            return restore_terms(out, mapping)

        llm_ok_text: Optional[str] = None
        if self.llm.available():
            candidate, status = self.llm.clean(rule_clean)
            if candidate:
                validation = validate_llm_output(rule_clean, candidate, mode=context.mode)
                if validation.ok:
                    llm_ok_text = candidate

        final_text = llm_ok_text if llm_ok_text is not None else rule_clean
        final_text = restore_spans(final_text, span_mapping)
        final_text = restore_terms(final_text, mapping)
        return final_text


_DEFAULT_PIPELINE: Optional[DictationPipeline] = None


def process_transcript(raw_text: str, context: DictationContext, cfg: Optional[DictationConfig] = None) -> str:
    global _DEFAULT_PIPELINE
    if cfg is not None or _DEFAULT_PIPELINE is None:
        _DEFAULT_PIPELINE = DictationPipeline(cfg or DictationConfig())
    return _DEFAULT_PIPELINE.process_transcript(raw_text, context)

