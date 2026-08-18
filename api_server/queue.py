from __future__ import annotations

import queue
import threading
import traceback
import uuid
from pathlib import Path

from .engine import TTSEngine
from .schemas import GenerationSettings, Voice
from .store import TaskStore, utc_now
from .voices import VoiceRegistry


class GenerationQueue:
    def __init__(self, engine: TTSEngine, registry: VoiceRegistry, store: TaskStore, output_dir: Path):
        self.engine = engine
        self.registry = registry
        self.store = store
        self.output_dir = output_dir
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._submit_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="indextts-gpu-worker", daemon=True)
        self._thread.start()

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def submit(self, voice: Voice, text: str, settings: GenerationSettings) -> dict:
        with self._submit_lock:
            task_id = uuid.uuid4().hex
            output = self.output_dir / f"{task_id}.wav"
            task = self.store.create(task_id, voice.code, text, settings.model_dump(), str(output))
            self._queue.put(task_id)
        return task

    def position(self, task_id: str) -> int | None:
        with self._queue.mutex:
            waiting = [item for item in self._queue.queue if item is not None]
        try:
            return waiting.index(task_id) + 1
        except ValueError:
            return None

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            task_id = self._queue.get()
            if task_id is None:
                return
            try:
                task = self.store.get(task_id)
                self.store.update(task_id, status="running", started_at=utc_now())
                voice = self.registry.get(task["voice"])
                prompt = self.registry.resolve_audio(voice)
                settings = GenerationSettings.model_validate(task["settings"])
                self.engine.synthesize(prompt, task["text"], Path(task["output_path"]), settings)
                self.store.update(task_id, status="succeeded", completed_at=utc_now())
            except Exception as exc:
                traceback.print_exc()
                self.store.update(task_id, status="failed", error=str(exc), completed_at=utc_now())
            finally:
                self._queue.task_done()
