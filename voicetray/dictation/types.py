from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


CleanupMode = Literal["raw", "balanced", "aggressive"]
FormatProfile = Literal["general", "email", "chat", "notes", "code/comments"]


@dataclass(frozen=True)
class DictationContext:
    mode: CleanupMode = "balanced"
    profile: FormatProfile = "general"
    app_title: Optional[str] = None

