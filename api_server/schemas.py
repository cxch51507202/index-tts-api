from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GenerationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    infer_mode: Literal["normal", "batch"] = "normal"
    do_sample: bool = True
    top_p: float = Field(default=0.8, ge=0.0, le=1.0)
    top_k: int = Field(default=30, ge=0, le=100)
    temperature: float = Field(default=1.0, ge=0.1, le=2.0)
    length_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    num_beams: int = Field(default=3, ge=1, le=10)
    repetition_penalty: float = Field(default=10.0, ge=0.1, le=20.0)
    max_mel_tokens: int = Field(default=600, ge=50, le=800)
    max_text_tokens_per_sentence: int = Field(default=80, ge=20, le=300)
    sentences_bucket_max_size: int = Field(default=2, ge=1, le=8)


class TTSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1)
    settings: GenerationSettings | None = None

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text cannot be blank")
        return value


class OpenAISpeechRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = "indextts-1.5"
    input: str = Field(min_length=1)
    voice: str = Field(min_length=1, max_length=64)
    response_format: Literal["wav"] = "wav"
    settings: GenerationSettings | None = None


class Voice(BaseModel):
    code: str
    name: str
    description: str = ""
    audio_path: str
    enabled: bool = True
    defaults: GenerationSettings = Field(default_factory=GenerationSettings)


class VoiceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None
    defaults: GenerationSettings | None = None


class TaskResponse(BaseModel):
    id: str
    sequence: int
    status: Literal["queued", "running", "succeeded", "failed"]
    queue_position: int | None = None
    voice: str
    text: str
    settings: dict[str, Any]
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    audio_url: str | None = None
    audio_path: str | None = None
