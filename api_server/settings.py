from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT_DIR / "api_config.json"


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    model_dir: Path
    voices_file: Path
    data_dir: Path
    output_dir: Path
    api_key_file: Path
    database_file: Path
    host: str
    port: int
    public_base_url: str
    max_text_length: int
    task_retention_days: int
    sync_timeout_seconds: int
    allowed_origins: tuple[str, ...]

    @property
    def api_key(self) -> str:
        env_key = os.environ.get("INDEXTTS_API_KEY", "").strip()
        if env_key:
            return env_key
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.api_key_file.exists():
            return self.api_key_file.read_text(encoding="utf-8").strip()
        key = f"itts_{secrets.token_urlsafe(32)}"
        self.api_key_file.write_text(key + "\n", encoding="utf-8")
        return key


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (root / path).resolve()


def load_settings(config_path: str | Path | None = None) -> Settings:
    path = Path(config_path or os.environ.get("INDEXTTS_API_CONFIG", DEFAULT_CONFIG_PATH))
    raw: dict[str, Any] = {}
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
    root = path.resolve().parent if path.exists() else ROOT_DIR
    data_dir = _resolve(root, raw.get("data_dir", "api_data"))
    return Settings(
        root_dir=root,
        model_dir=_resolve(root, raw.get("model_dir", "checkpoints")),
        voices_file=_resolve(root, raw.get("voices_file", "voices.json")),
        data_dir=data_dir,
        output_dir=_resolve(root, raw.get("output_dir", "outputs/api")),
        api_key_file=data_dir / "api_key.txt",
        database_file=data_dir / "tasks.sqlite3",
        host=os.environ.get("INDEXTTS_API_HOST", raw.get("host", "127.0.0.1")),
        port=int(os.environ.get("INDEXTTS_API_PORT", raw.get("port", 7870))),
        public_base_url=os.environ.get("INDEXTTS_PUBLIC_BASE_URL", raw.get("public_base_url", "")).rstrip("/"),
        max_text_length=int(raw.get("max_text_length", 5000)),
        task_retention_days=int(raw.get("task_retention_days", 7)),
        sync_timeout_seconds=int(raw.get("sync_timeout_seconds", 180)),
        allowed_origins=tuple(raw.get("allowed_origins", [])),
    )

