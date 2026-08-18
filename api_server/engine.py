from __future__ import annotations

import threading
from pathlib import Path
from typing import Protocol

from .schemas import GenerationSettings


class TTSEngine(Protocol):
    model_version: str | float | None
    device: str

    def synthesize(self, prompt: Path, text: str, output: Path, settings: GenerationSettings) -> Path: ...


class IndexTTSEngine:
    def __init__(self, model_dir: Path):
        from indextts.infer import IndexTTS

        self._lock = threading.Lock()
        self._tts = IndexTTS(
            model_dir=str(model_dir),
            cfg_path=str(model_dir / "config.yaml"),
            is_fp16=True,
            use_cuda_kernel=False,
        )
        self.model_version = self._tts.model_version or "1.5"
        self.device = str(self._tts.device)

    def synthesize(self, prompt: Path, text: str, output: Path, settings: GenerationSettings) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        kwargs = {
            "do_sample": settings.do_sample,
            "top_p": settings.top_p,
            "top_k": settings.top_k or None,
            "temperature": settings.temperature,
            "length_penalty": settings.length_penalty,
            "num_beams": settings.num_beams,
            "repetition_penalty": settings.repetition_penalty,
            "max_mel_tokens": settings.max_mel_tokens,
        }
        with self._lock:
            if settings.infer_mode == "batch":
                result = self._tts.infer_fast(
                    str(prompt), text, str(output),
                    max_text_tokens_per_sentence=settings.max_text_tokens_per_sentence,
                    sentences_bucket_max_size=settings.sentences_bucket_max_size,
                    **kwargs,
                )
            else:
                result = self._tts.infer(
                    str(prompt), text, str(output),
                    max_text_tokens_per_sentence=settings.max_text_tokens_per_sentence,
                    **kwargs,
                )
        return Path(result)

