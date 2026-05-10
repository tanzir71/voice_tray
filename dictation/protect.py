from __future__ import annotations

import re
from typing import Dict, Tuple


_SPAN_PATTERNS = [
    re.compile(r"```[\s\S]*?```"),
    re.compile(r"`[^`]*?`"),
    re.compile(r"\"[^\"\n]{1,200}\""),
]


def protect_spans(text: str) -> Tuple[str, Dict[str, str]]:
    if not text:
        return text, {}

    mapping: Dict[str, str] = {}
    out = text
    idx = 0

    changed = True
    while changed:
        changed = False
        for pattern in _SPAN_PATTERNS:
            m = pattern.search(out)
            if m is None:
                continue
            placeholder = f"__SPAN_{idx}__"
            idx += 1
            mapping[placeholder] = out[m.start() : m.end()]
            out = out[: m.start()] + placeholder + out[m.end() :]
            changed = True
            break

    return out, mapping


def restore_spans(text: str, mapping: Dict[str, str]) -> str:
    if not text or not mapping:
        return text
    out = text
    for placeholder, original in mapping.items():
        out = out.replace(placeholder, original)
    return out

