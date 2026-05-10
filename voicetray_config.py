from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class Settings:
    speech_hotkey: str = "f9"
    save_hotkey: str = "f10"
    start_with_windows: bool = False
    auto_start_listening: bool = True
    notification_duration: int = 3

    dictation_mode: str = "balanced"
    format_profile: str = "general"
    glossary_path: str = "glossary.json"
    app_profiles_path: str = "app_profiles.json"

    llm_enabled: bool = False
    llm_model_path: str = "models/llm/model.gguf"
    llm_n_ctx: int = 2048
    llm_max_tokens: int = 256
    llm_temperature: float = 0.05
    llm_top_p: float = 0.9
    llm_threads: Optional[int] = None
    llm_gpu_layers: Optional[int] = None


def _parse_bool(s: str) -> bool:
    return str(s).strip().lower() == "true"


def load_settings(path: str) -> Settings:
    base = Settings()
    if not path or not os.path.exists(path):
        return base
    values: Dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    except Exception:
        return base

    def get(key: str, default: str) -> str:
        return values.get(key, default)

    def get_int(key: str, default: int) -> int:
        try:
            return int(get(key, str(default)))
        except Exception:
            return default

    def get_float(key: str, default: float) -> float:
        try:
            return float(get(key, str(default)))
        except Exception:
            return default

    def get_opt_int(key: str) -> Optional[int]:
        if key not in values:
            return None
        try:
            return int(values[key])
        except Exception:
            return None

    return Settings(
        speech_hotkey=get("speech_hotkey", base.speech_hotkey),
        save_hotkey=get("save_hotkey", base.save_hotkey),
        start_with_windows=_parse_bool(get("start_with_windows", str(base.start_with_windows).lower())),
        auto_start_listening=_parse_bool(get("auto_start_listening", str(base.auto_start_listening).lower())),
        notification_duration=get_int("notification_duration", base.notification_duration),
        dictation_mode=get("dictation_mode", base.dictation_mode).lower(),
        format_profile=get("format_profile", base.format_profile).lower(),
        glossary_path=get("glossary_path", base.glossary_path),
        app_profiles_path=get("app_profiles_path", base.app_profiles_path),
        llm_enabled=_parse_bool(get("llm_enabled", str(base.llm_enabled).lower())),
        llm_model_path=get("llm_model_path", base.llm_model_path),
        llm_n_ctx=get_int("llm_n_ctx", base.llm_n_ctx),
        llm_max_tokens=get_int("llm_max_tokens", base.llm_max_tokens),
        llm_temperature=get_float("llm_temperature", base.llm_temperature),
        llm_top_p=get_float("llm_top_p", base.llm_top_p),
        llm_threads=get_opt_int("llm_threads"),
        llm_gpu_layers=get_opt_int("llm_gpu_layers"),
    )


def write_setting(path: str, key: str, value: str) -> bool:
    if not path:
        return False
    try:
        lines = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()

        key_found = False
        out_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in line:
                k, _v = line.split("=", 1)
                if k.strip() == key:
                    out_lines.append(f"{key}={value}")
                    key_found = True
                    continue
            out_lines.append(line)

        if not key_found:
            if out_lines and out_lines[-1].strip() != "":
                out_lines.append("")
            out_lines.append(f"{key}={value}")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out_lines) + "\n")
        return True
    except Exception:
        return False

