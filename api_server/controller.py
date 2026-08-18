from __future__ import annotations

import json
import secrets
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import request as urllib_request

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from .settings import ROOT_DIR


API_TASK_NAME = "IndexTTS Remote API"
CONTROLLER_TASK_NAME = "IndexTTS Local Controller"
TUNNEL_SERVICE_NAME = "Cloudflared"
API_PORT = 7870
CONTROLLER_PORT = 7871


def _run(args: list[str], timeout: float = 10.0) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return completed.returncode, (completed.stdout or completed.stderr or "").strip()
    except Exception as exc:
        return 1, str(exc)


def _powershell(script: str, timeout: float = 10.0) -> tuple[int, str]:
    return _run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        timeout,
    )


def _json_powershell(script: str) -> dict:
    code, output = _powershell(script)
    if code != 0 or not output:
        return {}
    try:
        value = json.loads(output)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _probe(url: str, timeout: float = 1.5) -> dict:
    started = time.monotonic()
    try:
        req = urllib_request.Request(url, headers={"Accept": "application/json"})
        with urllib_request.urlopen(req, timeout=timeout) as response:
            return {
                "reachable": response.status == 200,
                "status_code": response.status,
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


def _listener_pid(port: int) -> int | None:
    script = (
        f"$x=Get-NetTCPConnection -LocalPort {port} -State Listen "
        "-ErrorAction SilentlyContinue | Select-Object -First 1; "
        "if($x){$x.OwningProcess}"
    )
    code, output = _powershell(script, timeout=4.0)
    if code != 0 or not output:
        return None
    try:
        return int(output.splitlines()[-1].strip())
    except (TypeError, ValueError):
        return None


def _task_info() -> dict:
    script = (
        f"$t=Get-ScheduledTask -TaskName '{API_TASK_NAME}' -ErrorAction SilentlyContinue; "
        "$o=$null; if($t){$o=[pscustomobject]@{state=[string]$t.State; "
        "enabled=([bool]$t.Settings.Enabled)}}; "
        "$o | ConvertTo-Json -Compress"
    )
    return _json_powershell(script)


def _service_info() -> dict:
    script = (
        f"$s=Get-Service -Name '{TUNNEL_SERVICE_NAME}' -ErrorAction SilentlyContinue; "
        "$o=$null; if($s){$o=[pscustomobject]@{status=[string]$s.Status; "
        "start_type=[string]$s.StartType}}; $o | ConvertTo-Json -Compress"
    )
    return _json_powershell(script)


def _local_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def _api_process_info() -> dict:
    script = (
        "$p=Get-CimInstance Win32_Process | Where-Object {"
        "$_.Name -match '^python(w)?\\.exe$' -and "
        "$_.CommandLine -match 'api_server(\\.hidden_launcher)?'} | Select-Object -First 1; "
        "$o=$null; if($p){$o=[pscustomobject]@{pid=$p.ProcessId; name=$p.Name}}; "
        "$o | ConvertTo-Json -Compress"
    )
    return _json_powershell(script)


def _start_api() -> dict:
    if _probe("http://127.0.0.1:7870/health?format=json", timeout=0.8)["reachable"]:
        return {"ok": True, "message": "API 已经在运行。"}
    task = _task_info()
    if task.get("enabled"):
        code, output = _run(["schtasks.exe", "/Run", "/TN", API_TASK_NAME])
    else:
        vbs = ROOT_DIR / "start-api-hidden.vbs"
        if not vbs.is_file():
            return {"ok": False, "message": f"找不到启动脚本：{vbs}"}
        try:
            subprocess.Popen(
                ["wscript.exe", str(vbs)],
                cwd=str(ROOT_DIR),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                close_fds=True,
            )
            return {"ok": True, "message": "已发起 API 启动，模型加载需要一些时间。"}
        except Exception as exc:
            return {"ok": False, "message": f"启动 API 失败：{exc}"}
    return {
        "ok": code == 0,
        "message": "已发起 API 启动，模型加载需要一些时间。" if code == 0 else output,
    }


def _stop_api() -> dict:
    _run(["schtasks.exe", "/End", "/TN", API_TASK_NAME], timeout=8.0)
    time.sleep(0.5)
    pid = _listener_pid(API_PORT)
    if pid:
        code, output = _run(["taskkill.exe", "/PID", str(pid), "/T", "/F"], timeout=12.0)
        if code != 0 and _listener_pid(API_PORT):
            return {"ok": False, "message": output or "无法结束 API 进程，请以管理员身份运行控制器。"}
    return {"ok": True, "message": "API 已停止。"}


def _restart_api() -> dict:
    stopped = _stop_api()
    if not stopped["ok"]:
        return stopped
    time.sleep(1.0)
    return _start_api()


def _service_action(action: str) -> dict:
    current = _service_info().get("status")
    if action == "start" and current == "Running":
        return {"ok": True, "message": "Cloudflared 已经在运行。"}
    if action == "stop" and current == "Stopped":
        return {"ok": True, "message": "Cloudflared 已经停止。"}
    command = {
        "start": f"Start-Service -Name '{TUNNEL_SERVICE_NAME}' -ErrorAction Stop",
        "stop": f"Stop-Service -Name '{TUNNEL_SERVICE_NAME}' -Force -ErrorAction Stop",
        "restart": f"Restart-Service -Name '{TUNNEL_SERVICE_NAME}' -Force -ErrorAction Stop",
    }[action]
    code, output = _powershell(command, timeout=20.0)
    labels = {"start": "启动", "stop": "停止", "restart": "重启"}
    return {
        "ok": code == 0,
        "message": f"已发起 Cloudflared {labels[action]}。" if code == 0 else output,
    }


def create_controller_app() -> FastAPI:
    controller_app = FastAPI(title="IndexTTS 本机控制器", docs_url=None, redoc_url=None)
    controller_app.state.started_at = time.time()
    controller_app.state.control_token = secrets.token_urlsafe(32)
    controller_app.state.action_lock = threading.Lock()

    def require_local(request: Request) -> None:
        client_host = request.client.host if request.client else ""
        if client_host not in {"127.0.0.1", "::1", "localhost"}:
            raise HTTPException(status_code=404, detail="not found")

    def require_token(request: Request, token: str | None) -> None:
        require_local(request)
        if not token or not secrets.compare_digest(token, controller_app.state.control_token):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid controller token")

    def state() -> dict:
        task = _task_info()
        service = _service_info()
        api_probe = _probe("http://127.0.0.1:7870/health?format=json")
        tunnel_probe = _probe("http://127.0.0.1:20241/ready")
        api_pid = _listener_pid(API_PORT)
        api_process = _api_process_info()
        api_running = bool(api_probe["reachable"] or api_pid or api_process)
        api_phase = "online" if api_probe["reachable"] else "starting" if api_running else "stopped"
        return {
            "controller": {
                "status": "running",
                "port": CONTROLLER_PORT,
                "uptime_seconds": int(time.time() - controller_app.state.started_at),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            },
            "api": {
                "running": api_running,
                "phase": api_phase,
                "listener": bool(api_pid),
                "pid": api_pid or api_process.get("pid"),
                "port": API_PORT,
                "health": api_probe,
                "task_state": task.get("state", "unknown"),
                "autostart": bool(task.get("enabled", False)),
            },
            "tunnel": {
                "running": service.get("status") == "Running",
                "status": service.get("status", "unknown"),
                "start_type": service.get("start_type", "unknown"),
                "ready": tunnel_probe["reachable"],
                "ready_probe": tunnel_probe,
            },
        }

    @controller_app.get("/", response_class=HTMLResponse)
    @controller_app.get("/admin", response_class=HTMLResponse)
    def page(request: Request):
        require_local(request)
        path = Path(__file__).with_name("controller.html")
        html = path.read_text(encoding="utf-8").replace("__CONTROLLER_TOKEN__", controller_app.state.control_token)
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @controller_app.get("/status")
    def get_status(request: Request):
        require_local(request)
        return state()

    @controller_app.post("/api/{action}")
    def api_action(request: Request, action: str, x_index_tts_controller_token: str | None = Header(default=None)):
        require_token(request, x_index_tts_controller_token)
        if action not in {"start", "stop", "restart"}:
            raise HTTPException(status_code=404, detail="unknown action")
        with controller_app.state.action_lock:
            result = {"action": f"api_{action}", **globals()[f"_{action}_api"]()}
        return {**result, "state": state()}

    @controller_app.post("/tunnel/{action}")
    def tunnel_action(request: Request, action: str, x_index_tts_controller_token: str | None = Header(default=None)):
        require_token(request, x_index_tts_controller_token)
        if action not in {"start", "stop", "restart"}:
            raise HTTPException(status_code=404, detail="unknown action")
        with controller_app.state.action_lock:
            result = {"action": f"tunnel_{action}", **_service_action(action)}
        return {**result, "state": state()}

    @controller_app.post("/api-autostart/{action}")
    def api_autostart(request: Request, action: str, x_index_tts_controller_token: str | None = Header(default=None)):
        require_token(request, x_index_tts_controller_token)
        if action not in {"enable", "disable"}:
            raise HTTPException(status_code=404, detail="unknown action")
        switch = "/ENABLE" if action == "enable" else "/DISABLE"
        code, output = _run(["schtasks.exe", "/Change", "/TN", API_TASK_NAME, switch])
        return {
            "action": f"api_autostart_{action}",
            "ok": code == 0,
            "message": "已更新 API 开机启动设置。" if code == 0 else output,
            "state": state(),
        }

    @controller_app.post("/recover")
    def recover(request: Request, x_index_tts_controller_token: str | None = Header(default=None)):
        require_token(request, x_index_tts_controller_token)
        with controller_app.state.action_lock:
            tunnel = _service_action("start")
            if not tunnel["ok"]:
                result = {"ok": False, "message": tunnel["message"]}
            else:
                time.sleep(1.0)
                api = _start_api()
                result = {
                    "ok": api["ok"],
                    "message": "远程服务恢复已启动，请等待模型和 Tunnel 就绪。" if api["ok"] else api["message"],
                }
        return {"action": "recover", **result, "state": state()}

    return controller_app


app = create_controller_app()
