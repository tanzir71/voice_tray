from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Glossary:
    user_terms: Tuple[str, ...] = ()
    protected_terms: Tuple[str, ...] = ()
    replacements: Tuple[Tuple[str, str], ...] = ()

    def all_protected(self) -> Tuple[str, ...]:
        combined = list(self.protected_terms)
        for t in self.user_terms:
            if t not in combined:
                combined.append(t)
        combined.sort(key=len, reverse=True)
        return tuple(combined)


def load_glossary(path: str) -> Glossary:
    try:
        if not path:
            return Glossary()
        if not os.path.exists(path):
            return Glossary()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) if f.readable() else {}
        if not isinstance(data, dict):
            return Glossary()
        user_terms = data.get("user_terms", [])
        protected_terms = data.get("protected_terms", [])
        replacements = data.get("replacements", {})

        if not isinstance(user_terms, list):
            user_terms = []
        if not isinstance(protected_terms, list):
            protected_terms = []
        if not isinstance(replacements, dict):
            replacements = {}

        normalized_replacements: List[Tuple[str, str]] = []
        for k, v in replacements.items():
            if isinstance(k, str) and isinstance(v, str) and k:
                normalized_replacements.append((k, v))

        return Glossary(
            user_terms=tuple([t for t in user_terms if isinstance(t, str) and t]),
            protected_terms=tuple([t for t in protected_terms if isinstance(t, str) and t]),
            replacements=tuple(normalized_replacements),
        )
    except Exception:
        return Glossary()


def learn_word(path: str | os.PathLike[str], term: str) -> Glossary:
    normalized = _normalize_learned_term(term)
    glossary = load_glossary(os.fspath(path))
    if not normalized:
        return glossary

    existing = list(glossary.user_terms)
    existing_lower = {value.casefold() for value in existing}
    if normalized.casefold() not in existing_lower:
        existing.append(normalized)

    data = {
        "user_terms": existing,
        "protected_terms": list(glossary.protected_terms),
        "replacements": {src: dst for src, dst in glossary.replacements},
    }
    _write_glossary(path, data)
    return load_glossary(os.fspath(path))


def _normalize_learned_term(term: str) -> str:
    if not isinstance(term, str):
        return ""
    return re.sub(r"\s+", " ", term).strip()


def _write_glossary(path: str | os.PathLike[str], data: Dict[str, object]) -> None:
    glossary_path = Path(path)
    if glossary_path.parent != Path("."):
        glossary_path.parent.mkdir(parents=True, exist_ok=True)
    glossary_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def apply_replacements(text: str, glossary: Glossary) -> str:
    if not text or not glossary.replacements:
        return text
    out = text
    for src, dst in glossary.replacements:
        pattern = r"\b" + re.escape(src) + r"\b"
        out = re.sub(pattern, dst, out, flags=re.IGNORECASE)
    return out


def protect_terms(text: str, glossary: Glossary) -> Tuple[str, Dict[str, str]]:
    protected = glossary.all_protected()
    if not text or not protected:
        return text, {}

    mapping: Dict[str, str] = {}
    out = text
    idx = 0
    for term in protected:
        if not term.strip():
            continue
        placeholder = f"__GLOSSARY_{idx}__"
        idx += 1
        pattern = re.compile(re.escape(term), flags=re.IGNORECASE)
        if not pattern.search(out):
            continue
        match = pattern.search(out)
        if match is None:
            continue
        mapping[placeholder] = out[match.start() : match.end()]
        out = pattern.sub(placeholder, out)
    return out, mapping


def restore_terms(text: str, mapping: Dict[str, str]) -> str:
    if not text or not mapping:
        return text
    out = text
    for placeholder, original in mapping.items():
        out = out.replace(placeholder, original)
    return out

