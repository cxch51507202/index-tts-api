from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from .schemas import GenerationSettings, Voice


VOICE_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,63}$")
AUTO_VOICE_CODE_RE = re.compile(r"^S-HVIE00R(\d+)$")


class VoiceRegistry:
    def __init__(self, path: Path, root_dir: Path):
        self.path = path
        self.root_dir = root_dir
        self._lock = threading.RLock()
        self._voices: dict[str, Voice] = {}
        self.reload()

    def reload(self) -> None:
        with self._lock:
            if not self.path.exists():
                self.path.write_text('{"voices": []}\n', encoding="utf-8")
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            voices = {}
            for item in raw.get("voices", []):
                voice = Voice.model_validate(item)
                self._validate(voice)
                if voice.code in voices:
                    raise ValueError(f"duplicate voice code: {voice.code}")
                voices[voice.code] = voice
            self._voices = voices
            numbers = [
                int(match.group(1))
                for code in voices
                if (match := AUTO_VOICE_CODE_RE.fullmatch(code))
            ]
            self._next_auto_sequence = max(numbers, default=0) + 1

    def list(self, include_disabled: bool = False) -> list[Voice]:
        with self._lock:
            values = list(self._voices.values())
        if not include_disabled:
            values = [voice for voice in values if voice.enabled]
        def sort_key(voice: Voice):
            match = AUTO_VOICE_CODE_RE.fullmatch(voice.code)
            return (1, int(match.group(1))) if match else (0, voice.code)

        return sorted(values, key=sort_key)

    def get(self, code: str, include_disabled: bool = False) -> Voice:
        with self._lock:
            voice = self._voices.get(code)
        if voice is None or (not include_disabled and not voice.enabled):
            raise KeyError(code)
        return voice

    def resolve_audio(self, voice: Voice) -> Path:
        path = Path(voice.audio_path)
        resolved = path if path.is_absolute() else (self.root_dir / path).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"voice audio not found: {resolved}")
        return resolved

    def upsert(self, voice: Voice) -> Voice:
        self._validate(voice)
        with self._lock:
            self._voices[voice.code] = voice
            self._save()
        return voice

    def add(self, voice: Voice) -> Voice:
        self._validate(voice)
        with self._lock:
            if voice.code in self._voices:
                raise KeyError(voice.code)
            self._voices[voice.code] = voice
            self._save()
        return voice

    def generate_code(self) -> str:
        with self._lock:
            code = f"S-HVIE00R{self._next_auto_sequence:02d}"
            self._next_auto_sequence += 1
            return code

    def _validate(self, voice: Voice) -> None:
        if not VOICE_CODE_RE.fullmatch(voice.code):
            raise ValueError("voice code must start with a letter and contain only ASCII letters, digits, _ or -")
        self.resolve_audio(voice)

    def _save(self) -> None:
        payload = {"voices": [voice.model_dump(mode="json") for voice in self.list(include_disabled=True)]}
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(self.path)


def merge_settings(defaults: GenerationSettings, override: GenerationSettings | None) -> GenerationSettings:
    if override is None:
        return defaults.model_copy(deep=True)
    provided = override.model_fields_set
    merged = defaults.model_dump()
    for field in provided:
        merged[field] = getattr(override, field)
    return GenerationSettings.model_validate(merged)
