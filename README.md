# IndexTTS Remote API

<div align="center">
  <img src="assets/index_icon.png" width="160" alt="IndexTTS Remote API" />
  <h2>Remote text-to-speech API with voice management and queued generation</h2>
</div>

<p align="center"><a href="README.md">English</a> | <a href="README.zh-CN.md">简体中文</a></p>

This project turns one GPU host running IndexTTS into a remotely callable speech service. Remote clients send authenticated HTTP requests; they do not need to install the model or own a GPU. IndexTTS is the inference engine underneath the API, not the client-facing product.

## What the API Provides

- API-key protected remote text-to-speech over HTTP/HTTPS
- Reference-voice upload, naming, enable/disable, and per-voice settings
- A single-worker GPU queue for safe concurrent submissions
- Asynchronous tasks with IDs, status, queue position, and WAV downloads
- OpenAI-compatible `POST /v1/audio/speech` endpoint
- Local administration, Swagger docs at `/docs`, and health checks at `/health`

## Request Flow

1. A remote client sends text, a voice code, and an API key.
2. FastAPI authenticates the request and stores a task.
3. One GPU worker loads the reference voice and runs IndexTTS.
4. The service stores the WAV file and task status.
5. The client polls the task and downloads the audio.

Keep Uvicorn on `127.0.0.1:7870`; publish it through an HTTPS reverse proxy or tunnel that you control. Never expose the local controller on port `7871`.

## Required Environment

The server needs Python 3.10, CUDA-compatible PyTorch, an NVIDIA GPU, FFmpeg, IndexTTS model files, FastAPI/Uvicorn, and disk storage for voices, SQLite tasks, and generated WAV files.

Remote deployment additionally requires an HTTPS proxy or tunnel, optional domain/DNS, TLS certificates, firewall rules, rate limits, upload-size limits, and monitoring.

## What the Operator Must Provide

- GPU host, NVIDIA driver, CUDA runtime, and compatible PyTorch
- IndexTTS 1.5 model files downloaded into `checkpoints/`
- Reference recordings that the operator is authorized to use
- An API key through `INDEXTTS_API_KEY` or first-start generation
- Public URL and proxy/tunnel credentials for remote access
- Storage and cleanup policy for `api_data/` and `outputs/`
- TLS, firewall, rate limiting, backups, and uptime monitoring

The generated key is stored in `api_data/api_key.txt`; never commit or share it.

## Installation

```bash
git clone https://github.com/cxch51507202/index-tts-api.git
cd index-tts-api
conda create -n index-tts-api python=3.10
conda activate index-tts-api
conda install -c conda-forge ffmpeg pynini==2.1.6
pip install -e .
pip install -U huggingface_hub
huggingface-cli download IndexTeam/IndexTTS-1.5 config.yaml bigvgan_discriminator.pth bigvgan_generator.pth bpe.model dvae.pth gpt.pth unigram_12000.vocab --local-dir checkpoints
cp api_config.example.json api_config.json
cp voices.example.json voices.json
python -m api_server
```

## Remote Calls

Create an asynchronous task with `POST /api/v1/tts`, poll `GET /api/v1/tasks/{task_id}`, and download `GET /api/v1/tasks/{task_id}/audio`. These endpoints require `Authorization: Bearer YOUR_API_KEY`.

The OpenAI-compatible endpoint returns WAV bytes directly:

```bash
curl -X POST https://your-api.example.com/v1/audio/speech -H "Authorization: Bearer YOUR_API_KEY" -H "Content-Type: application/json" -d '{"model":"indextts-1.5","voice":"my_voice","input":"Remote speech test","response_format":"wav"}' -o output.wav
```

See [API_README.md](API_README.md) for complete voice, task, deployment, and security documentation.

## Security and Responsible Use

Only upload or synthesize voices with the speaker's informed consent. Do not use the service for fraud, impersonation, harassment, unlawful activity, or content that violates applicable law.

Source code is licensed under [Apache License 2.0](LICENSE). Model weights are governed by [INDEX_MODEL_LICENSE](INDEX_MODEL_LICENSE); commercial model use requires prior written authorization from the licensor.

## Engine and Acknowledgements

The inference engine comes from [IndexTTS](https://github.com/index-tts/index-tts) by bilibili Index. This project also acknowledges [Tortoise TTS](https://github.com/neonbjb/tortoise-tts), [Coqui TTS / XTTSv2](https://github.com/coqui-ai/TTS), [NVIDIA BigVGAN](https://github.com/NVIDIA/BigVGAN), [WeNet](https://github.com/wenet-e2e/wenet), [Icefall](https://github.com/k2-fsa/icefall), [FastAPI](https://github.com/fastapi/fastapi), [Uvicorn](https://github.com/Kludex/uvicorn), and [Gradio](https://github.com/gradio-app/gradio).
