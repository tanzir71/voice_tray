from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, List, Optional, Sequence, Tuple


FILLER_PHRASES_CONSERVATIVE: Tuple[str, ...] = (
    "um",
    "uh",
    "erm",
)

FILLER_PHRASES_AGGRESSIVE: Tuple[str, ...] = (
    *FILLER_PHRASES_CONSERVATIVE,
    "like",
    "you know",
    "basically",
    "sort of",
    "kind of",
)


SPOKEN_PUNCTUATION: Tuple[Tuple[str, str], ...] = (
    ("comma", ","),
    ("period", "."),
    ("full stop", "."),
    ("question mark", "?"),
    ("exclamation point", "!"),
    ("exclamation mark", "!"),
    ("colon", ":"),
    ("semicolon", ";"),
)


@dataclass(frozen=True)
class RuleOptions:
    remove_fillers: bool = True
    aggressive_fillers: bool = False
    remove_repetitions: bool = True
    handle_self_corrections: bool = True
    normalize_punctuation: bool = True
    normalize_capitalization: bool = True
    normalize_whitespace: bool = True
    enable_list_formatting: bool = False
    convert_spoken_punctuation: bool = True
    convert_spoken_newlines: bool = False
    final_period: bool = False


def normalize_whitespace(text: str) -> str:
    if not text:
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def convert_spoken_punctuation(text: str, convert_newlines: bool) -> str:
    if not text:
        return text
    out = " " + text + " "

    if convert_newlines:
        out = re.sub(r"\b(new line|newline)\b", "\n", out, flags=re.IGNORECASE)

    for spoken, punct in SPOKEN_PUNCTUATION:
        out = re.sub(r"\b" + re.escape(spoken) + r"\b", punct, out, flags=re.IGNORECASE)

    out = re.sub(r"\s+([,.!?;:])", r"\1", out)
    out = re.sub(r"([,.!?;:])([A-Za-z])", r"\1 \2", out)
    return out.strip()


def remove_fillers(text: str, aggressive: bool) -> str:
    if not text:
        return text
    out = " " + text + " "
    phrases = FILLER_PHRASES_AGGRESSIVE if aggressive else FILLER_PHRASES_CONSERVATIVE
    for phrase in sorted(phrases, key=len, reverse=True):
        out = re.sub(r"\b" + re.escape(phrase) + r"\b", " ", out, flags=re.IGNORECASE)
    out = re.sub(r"\s+", " ", out)
    return out.strip()


def remove_repetitions(text: str) -> str:
    if not text:
        return text
    words = text.split()
    if len(words) <= 1:
        return text

    cleaned_words = [words[0]]
    for i in range(1, len(words)):
        if words[i].lower() != words[i - 1].lower():
            cleaned_words.append(words[i])

    final_text = " ".join(cleaned_words)

    for phrase_len in [3, 2]:
        words = final_text.split()
        if len(words) < phrase_len * 2:
            continue
        cleaned: List[str] = []
        i = 0
        while i < len(words):
            if i + phrase_len * 2 <= len(words):
                phrase1 = " ".join(words[i : i + phrase_len])
                phrase2 = " ".join(words[i + phrase_len : i + phrase_len * 2])
                if phrase1.lower() == phrase2.lower():
                    cleaned.extend(words[i : i + phrase_len])
                    i += phrase_len * 2
                    continue
            cleaned.append(words[i])
            i += 1
        final_text = " ".join(cleaned)

    return final_text


def basic_grammar(text: str) -> str:
    if not text:
        return text
    text = text.strip()
    if not text:
        return text

    text = text[0].upper() + text[1:]
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"([,.!?;:])([a-zA-Z])", r"\1 \2", text)

    corrections = {
        r"\bi\b": "I",
        r"\bim\b": "I'm",
        r"\bive\b": "I've",
        r"\bill\b": "I'll",
        r"\bwont\b": "won't",
        r"\bcant\b": "can't",
        r"\bdont\b": "don't",
        r"\bisnt\b": "isn't",
        r"\barent\b": "aren't",
        r"\bwasnt\b": "wasn't",
        r"\bwerent\b": "weren't",
        r"\bhasnt\b": "hasn't",
        r"\bhavent\b": "haven't",
        r"\bhadnt\b": "hadn't",
        r"\bwouldnt\b": "wouldn't",
        r"\bcouldnt\b": "couldn't",
        r"\bshouldnt\b": "shouldn't",
    }

    for pattern, replacement in corrections.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text


SELF_CORRECTION_MARKERS: Tuple[str, ...] = (
    "no sorry",
    "no, sorry",
    "sorry",
    "i mean",
    "no actually",
    "actually",
)


def apply_self_corrections(text: str) -> str:
    if not text:
        return text
    lowered = text.lower()

    last_pos = -1
    last_marker: Optional[str] = None
    for marker in SELF_CORRECTION_MARKERS:
        pos = lowered.rfind(marker)
        if pos > last_pos:
            last_pos = pos
            last_marker = marker

    if last_pos < 0 or last_marker is None:
        return text

    before = text[:last_pos].strip(" ,")
    after = text[last_pos + len(last_marker) :].strip(" ,")
    if len(after.split()) < 2:
        return text

    similarity = SequenceMatcher(None, before.lower(), after.lower()).ratio() if before else 0.0
    if before and (len(before.split()) > 14 and similarity < 0.55):
        return text

    if after:
        return after
    return text


def maybe_format_list(text: str) -> str:
    if not text:
        return text
    lowered = text.lower()
    if "bullet" in lowered:
        parts = re.split(r"\bbullet\b", text, flags=re.IGNORECASE)
        items = [p.strip(" ,.-\n\t") for p in parts if p.strip(" ,.-\n\t")]
        if len(items) >= 2:
            return "\n".join([f"- {i[0].upper() + i[1:] if i else i}" for i in items])

    ordinals = ["first", "second", "third", "fourth", "fifth"]
    found = [o for o in ordinals if re.search(r"\b" + o + r"\b", lowered)]
    if len(found) >= 2:
        split_pattern = r"\b(?:" + "|".join(ordinals) + r")\b"
        parts = re.split(split_pattern, text, flags=re.IGNORECASE)
        items = [p.strip(" ,.-\n\t") for p in parts if p.strip(" ,.-\n\t")]
        if len(items) >= 2:
            return "\n".join([f"- {i[0].upper() + i[1:] if i else i}" for i in items])
    return text


def normalize_punctuation(text: str, final_period: bool) -> str:
    if not text:
        return text
    out = re.sub(r"\s+([,.!?;:])", r"\1", text)
    out = re.sub(r"([,.!?;:])([A-Za-z])", r"\1 \2", out)
    out = re.sub(r"\s+", " ", out).strip()
    if final_period and out and not re.search(r"[.!?]\s*$", out):
        out = out + "."
    return out


def apply_rules(text: str, options: RuleOptions) -> str:
    out = text
    if options.normalize_whitespace:
        out = normalize_whitespace(out)
    if options.convert_spoken_punctuation:
        out = convert_spoken_punctuation(out, convert_newlines=options.convert_spoken_newlines)
    if options.handle_self_corrections:
        out = apply_self_corrections(out)
    if options.remove_fillers:
        out = remove_fillers(out, aggressive=options.aggressive_fillers)
    if options.remove_repetitions:
        out = remove_repetitions(out)
    if options.normalize_capitalization:
        out = basic_grammar(out)
    if options.normalize_punctuation:
        out = normalize_punctuation(out, final_period=options.final_period)
    if options.enable_list_formatting:
        out = maybe_format_list(out)
    if options.normalize_whitespace:
        out = normalize_whitespace(out)
    return out

