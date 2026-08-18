from __future__ import annotations

import asyncio
import hmac
import shutil
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib import request as urllib_request

import torchaudio
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from .engine import IndexTTSEngine, TTSEngine
from .queue import GenerationQueue
from .schemas import GenerationSettings, OpenAISpeechRequest, TTSRequest, TaskResponse, Voice, VoiceUpdate
from .settings import Settings, load_settings
from .store import TaskStore
from .voices import VOICE_CODE_RE, VoiceRegistry, merge_settings


def probe_http(url: str, timeout: float) -> dict:
    started = time.monotonic()
    request = urllib_request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "IndexTTS-Health/1.0"},
    )
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            status_code = response.status
        return {
            "reachable": status_code == 200,
            "status_code": status_code,
            "latency_ms": round((time.monotonic() - started) * 1000),
            "error": None,
        }
    except Exception as exc:
        return {
            "reachable": False,
            "status_code": getattr(exc, "code", None),
            "latency_ms": round((time.monotonic() - started) * 1000),
            "error": str(exc),
        }


def create_app(
    settings: Settings | None = None,
    engine_factory: Callable[[Path], TTSEngine] = IndexTTSEngine,
) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        app.state.settings = settings
        app.state.registry = VoiceRegistry(settings.voices_file, settings.root_dir)
        app.state.store = TaskStore(settings.database_file)
        app.state.store.cleanup(settings.task_retention_days)
        app.state.engine = engine_factory(settings.model_dir)
        app.state.generation_queue = GenerationQueue(
            app.state.engine, app.state.registry, app.state.store, settings.output_dir
        )
        app.state.tunnel_probe = probe_http
        app.state.status_cache = {"expires_at": 0.0, "value": None}
        app.state.status_lock = threading.Lock()
        app.state.started_at = time.time()
        settings.api_key
        yield
        app.state.generation_queue.stop()

    app = FastAPI(
        title="IndexTTS Remote API",
        version="1.0.0",
        description="Authenticated voice registry and queued IndexTTS 1.5 inference API.",
        lifespan=lifespan,
    )

    def is_local_request(request: Request) -> bool:
        if request.headers.get("cf-ray"):
            return False
        return request.url.hostname in {"127.0.0.1", "localhost", "::1"}

    @app.get("/admin", include_in_schema=False, response_class=HTMLResponse)
    def admin_page(request: Request):
        if not is_local_request(request):
            raise HTTPException(status_code=404, detail="not found")
        admin_file = Path(__file__).with_name("admin.html")
        return HTMLResponse(admin_file.read_text(encoding="utf-8"))
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH"],
            allow_headers=["Authorization", "Content-Type", "X-API-Key"],
        )

    def require_api_key(
        request: Request,
        authorization: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None),
    ) -> None:
        if is_local_request(request):
            return
        supplied = x_api_key or ""
        if authorization and authorization.lower().startswith("bearer "):
            supplied = authorization[7:].strip()
        if not supplied or not hmac.compare_digest(supplied, settings.api_key):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")

    def task_response(request: Request, task: dict) -> TaskResponse:
        audio_url = None
        audio_path = None
        queue_position = None
        if task["status"] == "queued":
            queue_position = request.app.state.generation_queue.position(task["id"])
        if task["status"] == "succeeded":
            base = settings.public_base_url or str(request.base_url).rstrip("/")
            audio_path = f"/api/v1/tasks/{task['id']}/audio"
            audio_url = f"{base}{audio_path}"
        return TaskResponse(
            id=task["id"], sequence=task["sequence"], status=task["status"],
            queue_position=queue_position, voice=task["voice"], text=task["text"],
            settings=task["settings"], created_at=task["created_at"], started_at=task["started_at"],
            completed_at=task["completed_at"], error=task["error"], audio_url=audio_url,
            audio_path=audio_path,
        )

    def get_voice_and_settings(request: TTSRequest) -> tuple[Voice, GenerationSettings]:
        if len(request.text) > settings.max_text_length:
            raise HTTPException(status_code=422, detail=f"text exceeds {settings.max_text_length} characters")
        try:
            voice = app.state.registry.get(request.voice)
        except KeyError:
            raise HTTPException(status_code=404, detail="voice not found")
        return voice, merge_settings(voice.defaults, request.settings)

    def basic_health(request: Request) -> dict:
        engine = request.app.state.engine
        return {
            "status": "ok",
            "service": "indextts-api",
            "model_version": str(engine.model_version),
            "device": str(engine.device),
            "queue_depth": request.app.state.generation_queue.pending,
        }

    def full_health_status(request: Request) -> dict:
        cache = request.app.state.status_cache
        with request.app.state.status_lock:
            if cache["value"] is not None and time.monotonic() < cache["expires_at"]:
                return cache["value"]

            local = basic_health(request)
            probe = request.app.state.tunnel_probe
            connector = probe("http://127.0.0.1:20241/ready", 2.0)
            public_url = f"{settings.public_base_url}/health?format=json" if settings.public_base_url else ""
            public = (
                probe(public_url, 5.0)
                if public_url
                else {
                    "reachable": False,
                    "status_code": None,
                    "latency_ms": 0,
                    "error": "未配置公网地址",
                }
            )

            reasons = []
            if not connector["reachable"]:
                reasons.append("Cloudflare Tunnel 尚未建立连接。请确认 cloudflared 服务已启动，并检查当前网络或 VPN 节点是否允许 UDP/TCP 7844。")
            if connector["reachable"] and not public["reachable"]:
                reasons.append("Tunnel 已连接，但公网域名回环失败。请检查 Cloudflare 公网主机名、DNS 和源站映射。")
            if public.get("status_code") in {502, 530}:
                reasons.append(f"Cloudflare 返回 {public['status_code']}，通常表示边缘节点当前找不到可用的 Tunnel 连接。")

            overall_ok = connector["reachable"] and public["reachable"]
            value = {
                **local,
                "status": "ok" if overall_ok else "error",
                "local_api": True,
                "model_loaded": True,
                "uptime_seconds": int(time.time() - request.app.state.started_at),
                "task_counts": request.app.state.store.counts(),
                "public_url": settings.public_base_url,
                "tunnel_ready": connector["reachable"],
                "public_reachable": public["reachable"],
                "connector": connector,
                "public": public,
                "reasons": reasons,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            cache["value"] = value
            cache["expires_at"] = time.monotonic() + 5.0
            return value

    @app.get("/health")
    def health(request: Request, format: str | None = None):
        accepts_html = "text/html" in request.headers.get("accept", "").lower()
        if format == "json" or not accepts_html:
            return basic_health(request)
        health_file = Path(__file__).with_name("health.html")
        return HTMLResponse(health_file.read_text(encoding="utf-8"))

    @app.get("/health/status")
    def health_status(request: Request):
        return full_health_status(request)

    @app.get("/api/v1/info", dependencies=[Depends(require_api_key)])
    def info(request: Request):
        return {
            "service": "IndexTTS Remote API",
            "version": "1.0.0",
            "model": f"IndexTTS {request.app.state.engine.model_version}",
            "device": str(request.app.state.engine.device),
            "queue_depth": request.app.state.generation_queue.pending,
            "task_counts": request.app.state.store.counts(),
            "uptime_seconds": int(time.time() - request.app.state.started_at),
        }

    @app.get("/api/v1/settings/schema", dependencies=[Depends(require_api_key)])
    def settings_schema():
        return GenerationSettings.model_json_schema()

    @app.get("/api/v1/voices", dependencies=[Depends(require_api_key)])
    @app.get("/v1/audio/voices", dependencies=[Depends(require_api_key)])
    def list_voices(request: Request, include_disabled: bool = False):
        return [
            voice.model_dump(exclude={"audio_path"})
            for voice in request.app.state.registry.list(include_disabled=include_disabled)
        ]

    @app.post("/api/v1/voices", dependencies=[Depends(require_api_key)], status_code=201)
    async def create_voice(
        request: Request,
        code: str | None = Form(default=None),
        name: str = Form(...),
        description: str = Form(default=""),
        audio: UploadFile = File(...),
    ):
        code = (code or "").strip() or request.app.state.registry.generate_code()
        if not VOICE_CODE_RE.fullmatch(code):
            raise HTTPException(status_code=422, detail="invalid voice code")
        voices_dir = settings.data_dir / "voices"
        voices_dir.mkdir(parents=True, exist_ok=True)
        upload_path = voices_dir / f"{code}.upload"
        output_path = voices_dir / f"{code}.wav"
        with upload_path.open("wb") as target:
            shutil.copyfileobj(audio.file, target)
        try:
            waveform, sample_rate = torchaudio.load(str(upload_path))
            waveform = waveform.mean(dim=0, keepdim=True)
            waveform = torchaudio.functional.resample(waveform, sample_rate, 24000)
            waveform = waveform[:, : 12 * 24000]
            if waveform.shape[1] < 3 * 24000:
                raise ValueError("reference audio must be at least 3 seconds")
            torchaudio.save(str(output_path), waveform, 24000, encoding="PCM_S", bits_per_sample=16)
        except Exception as exc:
            output_path.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail=f"invalid audio: {exc}")
        finally:
            upload_path.unlink(missing_ok=True)
        relative = output_path.relative_to(settings.root_dir).as_posix()
        voice = Voice(code=code, name=name.strip(), description=description.strip(), audio_path=relative)
        try:
            request.app.state.registry.add(voice)
        except KeyError:
            output_path.unlink(missing_ok=True)
            raise HTTPException(status_code=409, detail="voice code already exists")
        return voice.model_dump(exclude={"audio_path"})

    @app.patch("/api/v1/voices/{code}", dependencies=[Depends(require_api_key)])
    def update_voice(request: Request, code: str, payload: VoiceUpdate):
        try:
            current = request.app.state.registry.get(code, include_disabled=True)
        except KeyError:
            raise HTTPException(status_code=404, detail="voice not found")
        changes = payload.model_dump(exclude_unset=True)
        if payload.defaults is not None:
            changes["defaults"] = merge_settings(current.defaults, payload.defaults)
        updated = current.model_copy(update=changes)
        request.app.state.registry.upsert(updated)
        return updated.model_dump(exclude={"audio_path"})

    @app.post(
        "/api/v1/tts",
        dependencies=[Depends(require_api_key)],
        status_code=202,
        response_model=TaskResponse,
    )
    def create_task(request: Request, payload: TTSRequest):
        voice, generation_settings = get_voice_and_settings(payload)
        task = request.app.state.generation_queue.submit(voice, payload.text, generation_settings)
        return task_response(request, task)

    @app.get(
        "/api/v1/tasks/{task_id}",
        dependencies=[Depends(require_api_key)],
        response_model=TaskResponse,
    )
    def get_task(request: Request, task_id: str):
        try:
            task = request.app.state.store.get(task_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="task not found")
        return task_response(request, task)

    @app.get("/api/v1/tasks/{task_id}/audio", dependencies=[Depends(require_api_key)])
    def get_audio(request: Request, task_id: str):
        try:
            task = request.app.state.store.get(task_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="task not found")
        if task["status"] != "succeeded":
            raise HTTPException(status_code=409, detail=f"task is {task['status']}")
        path = Path(task["output_path"])
        if not path.is_file():
            raise HTTPException(status_code=410, detail="audio file is no longer available")
        return FileResponse(path, media_type="audio/wav", filename=f"{task_id}.wav")

    @app.post("/v1/audio/speech", dependencies=[Depends(require_api_key)])
    async def openai_speech(request: Request, payload: OpenAISpeechRequest):
        normalized = TTSRequest(voice=payload.voice, text=payload.input, settings=payload.settings)
        voice, generation_settings = get_voice_and_settings(normalized)
        task = request.app.state.generation_queue.submit(voice, normalized.text, generation_settings)
        deadline = time.monotonic() + settings.sync_timeout_seconds
        while time.monotonic() < deadline:
            current = request.app.state.store.get(task["id"])
            if current["status"] == "succeeded":
                return FileResponse(current["output_path"], media_type="audio/wav", filename="speech.wav")
            if current["status"] == "failed":
                raise HTTPException(status_code=500, detail=current["error"] or "generation failed")
            await asyncio.sleep(0.25)
        raise HTTPException(status_code=504, detail="generation timed out; use the asynchronous task API")

    return app


app = create_app()
