from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple


FILLER_PHRASES_CONSERVATIVE: Tuple[str, ...] = (
    "um",
    "umm",
    "uh",
    "uhm",
    "erm",
    "er",
    "ah",
    "hmm",
    "mm",
    "mmm",
    "mhm",
)

FILLER_PHRASES_AGGRESSIVE: Tuple[str, ...] = (
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


def convert_spoken_punctuation(
    text: str,
    convert_newlines: bool,
    convert_punctuation: bool = True,
) -> str:
    if not text:
        return text
    out = " " + text + " "

    if convert_newlines:
        out = re.sub(r"\bnew paragraph\b", "\n\n", out, flags=re.IGNORECASE)
        out = re.sub(r"\b(new line|newline)\b", "\n", out, flags=re.IGNORECASE)

    if convert_punctuation:
        for spoken, punct in SPOKEN_PUNCTUATION:
            out = re.sub(r"\b" + re.escape(spoken) + r"\b", punct, out, flags=re.IGNORECASE)

    out = re.sub(r"[ \t\f\v]+([,.!?;:])", r"\1", out)
    out = re.sub(r"([,.!?;:])([A-Za-z])", r"\1 \2", out)
    return out.strip()


def remove_fillers(text: str, aggressive: bool) -> str:
    if not text:
        return text
    out = text

    for phrase in sorted(FILLER_PHRASES_CONSERVATIVE, key=len, reverse=True):
        out = _remove_high_confidence_filler(out, phrase)

    if aggressive:
        for phrase in sorted(FILLER_PHRASES_AGGRESSIVE, key=len, reverse=True):
            out = _remove_ambiguous_filler(out, phrase)

    return _normalize_filler_spacing(out)


def _remove_high_confidence_filler(text: str, phrase: str) -> str:
    pattern = _phrase_pattern(phrase, consume_trailing_comma=True)
    return re.sub(pattern, " ", text, flags=re.IGNORECASE)


def _remove_ambiguous_filler(text: str, phrase: str) -> str:
    pattern = _phrase_pattern(phrase, consume_trailing_comma=True)

    def replace(match: re.Match[str]) -> str:
        before_word = _last_word(text[: match.start()])
        after_word = _first_word(text[match.end() :])
        at_start = before_word is None
        if _should_remove_ambiguous_filler(phrase, before_word, after_word, at_start):
            return " "
        return match.group(0)

    return re.sub(pattern, replace, text, flags=re.IGNORECASE)


def _phrase_pattern(phrase: str, *, consume_trailing_comma: bool = False) -> str:
    words = [re.escape(part) for part in phrase.split()]
    pattern = r"(?<!\w)" + r"[\s,]+".join(words) + r"(?!\w)"
    if consume_trailing_comma:
        pattern += r"\s*,?"
    return pattern


def _should_remove_ambiguous_filler(
    phrase: str,
    before_word: str | None,
    after_word: str | None,
    at_start: bool,
) -> bool:
    before = before_word.lower() if before_word else None
    after = after_word.lower() if after_word else None

    if phrase == "basically":
        return True

    if phrase == "like":
        return at_start or before in {"is", "are", "was", "were", "be", "been", "being"}

    if phrase == "you know":
        return after not in {
            "a",
            "an",
            "the",
            "this",
            "that",
            "these",
            "those",
            "what",
            "when",
            "where",
            "why",
            "how",
            "my",
            "your",
            "his",
            "her",
            "our",
            "their",
        }

    if phrase in {"sort of", "kind of"}:
        return before not in {"a", "an", "the", "this", "that", "these", "those", "some", "any"}

    return False


def _last_word(text: str) -> str | None:
    matches = list(WORD_RE.finditer(text))
    if not matches:
        return None
    return matches[-1].group(0)


def _first_word(text: str) -> str | None:
    match = WORD_RE.search(text)
    if match is None:
        return None
    return match.group(0)


def _normalize_filler_spacing(text: str) -> str:
    out = re.sub(r"\s+([,.!?;:])", r"\1", text)
    out = re.sub(r"[ \t\f\v]+", " ", out)
    out = re.sub(r"[ \t]*\n[ \t]*", "\n", out)
    return out.strip(" ,")


def remove_repetitions(text: str) -> str:
    if not text:
        return text
    if "\n" in text:
        parts = re.split(r"(\n+)", text)
        return "".join(part if part.startswith("\n") else remove_repetitions(part) for part in parts)

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

    text = re.sub(
        r"(^|[.!?]\s+|\n+[ \t]*)([a-z])",
        lambda match: match.group(1) + match.group(2).upper(),
        text,
    )
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"[ \t\f\v]+([,.!?;:])", r"\1", text)
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


SELF_CORRECTION_MARKERS: Tuple[Tuple[str, str], ...] = (
    ("scratch that", r"\bscratch[\s,]+that\b"),
    ("no actually", r"\bno[\s,]+actually\b"),
    ("no sorry", r"\bno[\s,]+sorry\b"),
    ("no wait", r"\bno[\s,]+wait\b"),
    ("i mean", r"\bi[\s,]+mean\b"),
    ("actually", r"\bactually\b"),
    ("sorry", r"\bsorry\b"),
)

MAX_SELF_CORRECTION_REPLACEMENT_WORDS = 6
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")

FALSE_REPLACEMENT_STARTS = {
    "and",
    "but",
    "or",
    "so",
    "because",
    "if",
    "when",
    "while",
    "is",
    "are",
    "was",
    "were",
    "am",
    "be",
    "been",
    "being",
    "appears",
    "appeared",
}

NO_WAIT_FALSE_STARTS = {
    "for",
    "list",
    "time",
}

LINKING_OR_SPEECH_VERBS = {
    "am",
    "are",
    "be",
    "been",
    "being",
    "is",
    "said",
    "say",
    "says",
    "was",
    "were",
}


def apply_self_corrections(text: str) -> str:
    if not text:
        return text

    marker_match = _find_last_self_correction_marker(text)
    if marker_match is None:
        return text

    marker, start, end = marker_match
    before_words = _words(text[:start])
    after_words = _words(text[end:])
    if not before_words or not _is_plausible_replacement(marker, before_words, after_words):
        return text

    replacement_len = len(after_words)
    keep_words = before_words[:-replacement_len]
    corrected_words = [*keep_words, *after_words]
    if not corrected_words:
        return text

    return " ".join(corrected_words)


def _find_last_self_correction_marker(text: str) -> Tuple[str, int, int] | None:
    matches: List[Tuple[int, int, str]] = []
    for marker, pattern in SELF_CORRECTION_MARKERS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            matches.append((match.start(), match.end(), marker))
    if not matches:
        return None

    start, end, marker = max(matches, key=lambda item: (item[1], item[1] - item[0]))
    return marker, start, end


def _words(text: str) -> List[str]:
    return [match.group(0) for match in WORD_RE.finditer(text)]


def _is_plausible_replacement(marker: str, before_words: List[str], after_words: List[str]) -> bool:
    if not after_words:
        return False

    replacement_len = len(after_words)
    if replacement_len > MAX_SELF_CORRECTION_REPLACEMENT_WORDS:
        return False

    if len(before_words) < replacement_len:
        return False

    first_after = after_words[0].lower()
    if first_after in FALSE_REPLACEMENT_STARTS:
        return False

    if marker == "no wait" and first_after in NO_WAIT_FALSE_STARTS:
        return False

    if before_words[-1].lower() in LINKING_OR_SPEECH_VERBS:
        return False

    return True


def maybe_format_list(text: str) -> str:
    if not text:
        return text
    lowered = text.lower()
    bullet_pattern = r"\b(?:new\s+)?bullet(?:\s+point)?\b"
    if re.search(bullet_pattern, lowered, flags=re.IGNORECASE):
        parts = re.split(bullet_pattern, text, flags=re.IGNORECASE)
        items = [p.strip(" ,.-\n\t") for p in parts if p.strip(" ,.-\n\t")]
        if len(items) >= 2:
            return "\n".join([f"- {_capitalize_item(i)}" for i in items])

    numbered = _format_numbered_list(text)
    return numbered if numbered is not None else text


NUMBER_MARKERS = {
    "1": 1,
    "one": 1,
    "first": 1,
    "2": 2,
    "two": 2,
    "second": 2,
    "3": 3,
    "three": 3,
    "third": 3,
    "4": 4,
    "four": 4,
    "fourth": 4,
    "5": 5,
    "five": 5,
    "fifth": 5,
    "6": 6,
    "six": 6,
    "sixth": 6,
    "7": 7,
    "seven": 7,
    "seventh": 7,
    "8": 8,
    "eight": 8,
    "eighth": 8,
    "9": 9,
    "nine": 9,
    "ninth": 9,
    "10": 10,
    "ten": 10,
    "tenth": 10,
}

NUMBER_MARKER_RE = re.compile(
    r"(?<!\w)(?:number\s+)?("
    + "|".join(sorted((re.escape(marker) for marker in NUMBER_MARKERS), key=len, reverse=True))
    + r")\.?(?!\w)",
    flags=re.IGNORECASE,
)


def _format_numbered_list(text: str) -> str | None:
    matches = list(NUMBER_MARKER_RE.finditer(text))
    if len(matches) < 2:
        return None

    first_prefix = text[: matches[0].start()].strip(" ,:-\n\t")
    if first_prefix:
        return None

    numbers = [_marker_number(match) for match in matches]
    if numbers[0] != 1:
        return None
    if any(current != previous + 1 for previous, current in zip(numbers, numbers[1:])):
        return None

    items: List[str] = []
    for index, match in enumerate(matches):
        item_start = match.end()
        item_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        item = text[item_start:item_end].strip(" ,.-:\n\t")
        if not item:
            return None
        items.append(item)

    return "\n".join(f"{number}. {_capitalize_item(item)}" for number, item in zip(numbers, items))


def _marker_number(match: re.Match[str]) -> int:
    return NUMBER_MARKERS[match.group(1).lower()]


def _capitalize_item(item: str) -> str:
    if not item:
        return item
    return item[0].upper() + item[1:]


def normalize_punctuation(text: str, final_period: bool) -> str:
    if not text:
        return text
    out = re.sub(r"[ \t\f\v]+([,.!?;:])", r"\1", text)
    out = re.sub(r"([,.!?;:])([A-Za-z])", r"\1 \2", out)
    out = re.sub(r"[ \t\f\v]+", " ", out)
    out = re.sub(r"[ \t]*\n[ \t]*", "\n", out).strip()
    if final_period and out and not re.search(r"[.!?]\s*$", out):
        out = out + "."
    return out


def apply_rules(text: str, options: RuleOptions) -> str:
    out = text
    if options.normalize_whitespace:
        out = normalize_whitespace(out)
    if options.convert_spoken_punctuation or options.convert_spoken_newlines:
        out = convert_spoken_punctuation(
            out,
            convert_newlines=options.convert_spoken_newlines,
            convert_punctuation=options.convert_spoken_punctuation,
        )
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

