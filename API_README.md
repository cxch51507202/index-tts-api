# IndexTTS Remote API

This service wraps the local IndexTTS 1.5 model with API-key authentication,
a persistent voice registry, and a single GPU worker queue suitable for an 8 GB GPU.

## Start

Run `start-api.cmd`, or:

```powershell
.\.venv\Scripts\python.exe -m api_server
```

Local endpoints:

- API: `http://127.0.0.1:7870`
- Swagger: `http://127.0.0.1:7870/docs`
- Health: `http://127.0.0.1:7870/health`
- Local controller: `http://127.0.0.1:7871/admin`

Opening `/health` in a browser shows a status dashboard. It checks the local API,
loaded model, and GPU queue. If `public_base_url` is configured, it also reports
whether that URL is reachable. JSON clients can use `/health?format=json`; the
detailed dashboard data is available from `GET /health/status`.

The first startup creates the API key in `api_data/api_key.txt`. Keep this file private.
You can override it with the `INDEXTTS_API_KEY` environment variable.

For local browser management, open:

```text
http://127.0.0.1:7870/admin
```

The local page does not require an API key. It can upload reference audio, list
voices, enable/disable voices, submit a test task, and play the generated WAV.
The page returns `404` through the public hostname, and public API calls still
require the API key.

## Local service controller

`http://127.0.0.1:7871/admin` is a separate lightweight controller. It does not
load the model or use GPU memory, so it remains available when the API on port
7870 is stopped. It can start, stop, or restart the IndexTTS API and the
Cloudflared service, and can enable or disable API startup at Windows logon.

The controller binds only to `127.0.0.1`; it is not published by Cloudflare and
its state-changing requests require a per-page local controller token. The
public health page intentionally remains read-only.

The controller is started at Windows logon by the `IndexTTS Local Controller`
scheduled task. To install or repair that task, run PowerShell as Administrator:

```powershell
Set-Location "path\to\index-tts-1.5"
.\install-local-controller.ps1
```

You can also double-click `open-local-controller.cmd` to start the controller
on demand and open its page.

## Voice registry

Voices are stored in `voices.json`. Each voice has:

- `code`: stable unique identifier used by remote clients
- `name`: editable Chinese display name
- `description`: usage notes
- `audio_path`: local reference WAV file
- `enabled`: whether remote generation is allowed
- `defaults`: per-voice inference defaults

The initial voice is:

```text
code: wang_liqun
name: 王立群
```

List voices:

```powershell
$base = "http://127.0.0.1:7870"
$key = Get-Content .\api_data\api_key.txt -Raw
Invoke-RestMethod "$base/api/v1/voices" -Headers @{ Authorization = "Bearer $($key.Trim())" }
```

Upload a new voice. The server converts it to 24 kHz mono WAV and keeps at most 12 seconds:

```bash
curl -X POST http://127.0.0.1:7870/api/v1/voices \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "name=历史男声二号" \
  -F "description=沉稳、适合纪录片" \
  -F "audio=@reference.wav"
```

The reference audio must be at least 3 seconds. The server generates immutable,
sequential codes such as `S-HVIE00R01`, `S-HVIE00R02`, and `S-HVIE00R03` when
`code` is omitted. API clients may still provide an ASCII code explicitly;
attempting to reuse an existing code returns `409 Conflict`. Use
`GET /api/v1/voices` to confirm the Chinese name and generated code before
submitting TTS tasks.

Update a voice without changing its unique code:

```http
PATCH /api/v1/voices/wang_liqun
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "name": "王立群历史讲述",
  "enabled": true,
  "defaults": {
    "temperature": 0.9,
    "max_text_tokens_per_sentence": 80
  }
}
```

## Asynchronous generation

Create a task:

```http
POST /api/v1/tts
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "voice": "wang_liqun",
  "text": "这里是需要生成的文本。",
  "settings": {
    "infer_mode": "normal",
    "temperature": 1.0
  }
}
```

The response contains a task ID. Poll `GET /api/v1/tasks/{task_id}` until
`status` is `succeeded`, then download `audio_url`. Tasks are processed one at a
time to avoid exhausting GPU memory.

The default inference mode is `normal`, which processes sentences one at a time.
A request can select `batch` explicitly when faster bucketed inference is preferred.

The asynchronous endpoint accepts multiple requests at the same time. Each request
returns immediately with a task ID (`202 Accepted`); the single GPU worker then
generates tasks in submission order. Poll each task independently and download its
WAV when it reaches `succeeded`. This lets a remote client submit a batch without
holding open one HTTP request per audio file.

Every task response includes both `id` and `sequence`. `id` is the immutable unique
identifier used in query/download URLs, while `sequence` is an increasing number
that represents server submission order. Queued responses also include the current
one-based `queue_position` when available.

The OpenAI-compatible `/v1/audio/speech` endpoint is intentionally synchronous and
waits for one result. Use `/api/v1/tts` for concurrent submission and queueing.

## OpenAI-compatible synchronous endpoint

```http
POST /v1/audio/speech
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "model": "indextts-1.5",
  "voice": "wang_liqun",
  "input": "这是同步接口测试。",
  "response_format": "wav"
}
```

This endpoint waits for the result and directly returns WAV bytes. For long text
or unstable networks, use the asynchronous task API.

## Remote deployment

The API binds to `127.0.0.1` by default. For a remote deployment, put it behind
an authenticated reverse proxy or a tunnel that you control, set
`public_base_url` to the externally reachable URL, and protect the API key. Do
not expose the local controller or publish `api_data/`.

From another computer, set the remote URL and key, then call the same endpoints:

```powershell
$base = "https://your-api.example.com"
$key = "YOUR_API_KEY"
$headers = @{ Authorization = "Bearer $key" }

# Discover registered voices and their Chinese names/codes.
Invoke-RestMethod "$base/api/v1/voices" -Headers $headers

# Discover the inference settings accepted by the server.
Invoke-RestMethod "$base/api/v1/settings/schema" -Headers $headers
```

`GET /health` is public for uptime checks. Voice data, settings, task submission,
task status, and generated audio require a valid API key. Review your deployment
provider's TLS, access-control, request-size, and rate-limit settings before
exposing the service to the internet.
