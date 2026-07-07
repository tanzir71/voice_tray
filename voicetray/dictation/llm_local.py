from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


SYSTEM_PROMPT = (
    "You are a transcription cleanup engine.\n"
    "Task: minimally clean a speech-to-text transcript to read like written text.\n"
    "Hard rules:\n"
    "- Preserve meaning exactly; never add missing information.\n"
    "- Keep names, numbers, acronyms, technical terms unchanged.\n"
    "- Do not rewrite protected tokens like __GLOSSARY_#__ or __SPAN_#__ (code/quoted text).\n"
    "- Prefer tiny edits: punctuation, capitalization, light grammar, self-corrections.\n"
    "- Output ONLY valid JSON: {\"text\": \"...\"}. No extra keys, no commentary.\n"
)


def build_cleanup_prompt(text: str, *, tone_hint: str = "neutral") -> str:
    return (
        "Clean this transcript conservatively. Return JSON only.\n"
        f"Tone hint: {tone_hint}. Apply this only when it does not change meaning.\n"
        f"TRANSCRIPT:\n{text}"
    )


@dataclass(frozen=True)
class LocalLLMConfig:
    enabled: bool = False
    model_path: str = ""
    n_ctx: int = 2048
    max_tokens: int = 256
    temperature: float = 0.05
    top_p: float = 0.9
    n_threads: Optional[int] = None
    n_gpu_layers: Optional[int] = None


class LocalLLMCleaner:
    def __init__(self, cfg: LocalLLMConfig):
        self.cfg = cfg
        self._model = None

    def available(self) -> bool:
        if not self.cfg.enabled or not self.cfg.model_path:
            return False
        try:
            import llama_cpp  # noqa: F401

            return True
        except Exception:
            return False

    def _load(self):
        if self._model is not None:
            return
        from llama_cpp import Llama

        kwargs: Dict[str, Any] = {
            "model_path": self.cfg.model_path,
            "n_ctx": self.cfg.n_ctx,
        }
        if self.cfg.n_threads is not None:
            kwargs["n_threads"] = self.cfg.n_threads
        if self.cfg.n_gpu_layers is not None:
            kwargs["n_gpu_layers"] = self.cfg.n_gpu_layers
        self._model = Llama(**kwargs)

    def clean(self, text: str, *, tone_hint: str = "neutral") -> Tuple[Optional[str], str]:
        if not self.available():
            return None, "disabled"
        try:
            self._load()
            model = self._model
            if model is None:
                return None, "not_loaded"

            user_prompt = build_cleanup_prompt(text, tone_hint=tone_hint)

            if hasattr(model, "create_chat_completion"):
                resp = model.create_chat_completion(
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self.cfg.temperature,
                    top_p=self.cfg.top_p,
                    max_tokens=self.cfg.max_tokens,
                )
                content = resp["choices"][0]["message"]["content"]
            else:
                prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}\n\nJSON:" 
                resp = model(
                    prompt,
                    temperature=self.cfg.temperature,
                    top_p=self.cfg.top_p,
                    max_tokens=self.cfg.max_tokens,
                    stop=["\n\n"],
                )
                content = resp["choices"][0]["text"]

            content = content.strip()
            data = json.loads(content)
            if not isinstance(data, dict) or "text" not in data or not isinstance(data["text"], str):
                return None, "bad_json"
            return data["text"], "ok"
        except Exception as e:
            return None, f"error:{type(e).__name__}"

