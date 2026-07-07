"""Whisper model download helpers for source and packaged runs."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config import load_config

ProgressCallback = Callable[[int], None]
ModelFactory = Callable[..., Any]


def default_models_dir(models_dir: str | Path | None = None) -> Path:
    if models_dir is not None:
        return Path(models_dir)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "models"
    return Path(__file__).resolve().parents[1] / "models"


def download_whisper_model(
    model_size: str,
    progress_callback: ProgressCallback | None = None,
    *,
    model_factory: ModelFactory | None = None,
    models_dir: str | Path | None = None,
    config: dict[str, Any] | None = None,
) -> Path:
    cfg = config if config is not None else load_config()
    stt = cfg.get("stt", {}) if isinstance(cfg, dict) else {}
    target = default_models_dir(models_dir) / "whisper"
    target.mkdir(parents=True, exist_ok=True)

    _emit_progress(progress_callback, 5)
    factory = model_factory or _default_model_factory
    factory(
        str(model_size),
        device=str(stt.get("device", "cpu")),
        compute_type=str(stt.get("compute_type", "int8")),
        local_files_only=False,
        download_root=str(target),
    )
    _emit_progress(progress_callback, 100)
    return target


def _emit_progress(callback: ProgressCallback | None, value: int) -> None:
    if callback is not None:
        callback(int(value))


def _default_model_factory(*args: Any, **kwargs: Any) -> Any:
    from faster_whisper import WhisperModel

    return WhisperModel(*args, **kwargs)
