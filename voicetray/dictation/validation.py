from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Sequence, Set, Tuple


def extract_numbers(text: str) -> List[str]:
    return re.findall(r"\b\d+(?:[.,]\d+)?\b", text or "")


def extract_urls(text: str) -> List[str]:
    return re.findall(r"https?://[^\s)>\]]+", text or "")


def extract_words(text: str) -> List[str]:
    return re.findall(r"[A-Za-z][A-Za-z']*", text or "")


def has_same_placeholders(a: str, b: str) -> bool:
    pa = set(re.findall(r"__GLOSSARY_\d+__", a or ""))
    pb = set(re.findall(r"__GLOSSARY_\d+__", b or ""))
    sa = set(re.findall(r"__SPAN_\d+__", a or ""))
    sb = set(re.findall(r"__SPAN_\d+__", b or ""))
    return pa == pb and sa == sb


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str


def validate_llm_output(rule_text: str, llm_text: str, mode: str) -> ValidationResult:
    if not llm_text:
        return ValidationResult(False, "empty")
    if not has_same_placeholders(rule_text, llm_text):
        return ValidationResult(False, "glossary_changed")

    if extract_numbers(rule_text) != extract_numbers(llm_text):
        return ValidationResult(False, "numbers_changed")

    a = rule_text.strip()
    b = llm_text.strip()

    if extract_urls(a) != extract_urls(b):
        return ValidationResult(False, "urls_changed")

    if a and b:
        length_ratio = len(b) / len(a)
        if length_ratio < 0.6 or length_ratio > 1.4:
            return ValidationResult(False, "length_ratio")

    ratio = SequenceMatcher(None, a, b).ratio() if a and b else 0.0
    min_ratio = 0.75 if mode == "balanced" else 0.65
    if ratio < min_ratio:
        return ValidationResult(False, "too_different")

    a_words = [w.lower() for w in extract_words(a)]
    b_words = [w.lower() for w in extract_words(b)]
    a_set = set(a_words)
    b_set = set(b_words)
    added = [w for w in b_set.difference(a_set) if len(w) > 2]
    if a_words:
        if len(added) > max(2, int(0.05 * len(a_set))):
            return ValidationResult(False, "added_words")

    return ValidationResult(True, "ok")

