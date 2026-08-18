# IndexTTS Remote API

<div align="center">
  <img src="assets/index_icon.png" width="180" alt="IndexTTS" />
  <h2>可远程调用的文本转语音 API 服务</h2>
</div>

<p align="center">
  简体中文 · <a href="README.md">English</a>
</p>

<p align="center">
  <a href="https://arxiv.org/abs/2502.05512"><img src="https://img.shields.io/badge/arXiv-2502.05512-b31b1b" alt="论文" /></a>
  <a href="https://github.com/index-tts/index-tts"><img src="https://img.shields.io/badge/upstream-index--tts-181717?logo=github" alt="上游项目" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/code-Apache--2.0-green" alt="Apache 2.0" /></a>
</p>

> 本项目把一台运行 IndexTTS 的 GPU 主机变成可远程调用的语音服务。远程客户端只需发送经过鉴权的 HTTP 请求，不需要安装模型或拥有 GPU。IndexTTS 是 API 底层推理引擎，API 服务才是面向用户的产品。

## API 服务能做什么

- 通过 HTTP/HTTPS 远程提交文本转语音请求
- 上传、命名、启用、停用和配置参考音色
- 使用单 GPU 工作队列，避免并发任务耗尽显存
- 异步任务返回 ID、状态、队列位置并下载 WAV
- 提供兼容 OpenAI 的 `POST /v1/audio/speech` 接口
- 提供本地管理页、`/docs` Swagger 文档和 `/health` 健康检查

## 工作原理

1. 远程客户端发送文本、音色代码和 API Key。
2. FastAPI 校验密钥并创建任务。
3. 单个 GPU Worker 加载参考音频并运行 IndexTTS。
4. 服务保存 WAV 文件和任务状态。
5. 客户端轮询任务并下载音频。

Uvicorn 默认监听 `127.0.0.1:7870`，远程访问应通过你自己控制的 HTTPS 反向代理或 Tunnel 发布。`7871` 本地控制器端口不能公开。

## 服务、环境与用户需要提供的内容

服务端需要 Python 3.10、兼容 CUDA 的 PyTorch、NVIDIA GPU、FFmpeg、IndexTTS 模型文件、FastAPI/Uvicorn，以及保存音色、SQLite 任务和 WAV 的磁盘空间。远程部署还需要 HTTPS 代理或 Tunnel、可选的域名/DNS、TLS、防火墙、限流、上传大小限制和监控。

用户需要提供 GPU 主机和驱动、放入 `checkpoints/` 的模型权重、获得授权的参考录音、API Key、远程 URL 与代理凭据、存储清理策略、TLS、防火墙、备份和可用性监控。自动生成的密钥位于 `api_data/api_key.txt`，绝不能提交或公开。

## 远程调用

使用 `POST /api/v1/tts` 创建异步任务，再轮询 `GET /api/v1/tasks/{task_id}` 并从 `GET /api/v1/tasks/{task_id}/audio` 下载。兼容 OpenAI 的 `POST /v1/audio/speech` 会直接返回 WAV。完整接口、部署和安全说明见 [API_README.md](API_README.md)。

## 主要特性

- 使用短参考音频进行零样本音色复刻
- 字符-拼音混合建模，便于修正中文发音
- 根据标点控制停顿，支持多项推理参数调节
- Conformer 说话人条件编码器与 BigVGAN2 解码器
- 支持命令行、Gradio WebUI 和队列式 API 服务
- 提供兼容 OpenAI 的 `/v1/audio/speech` 接口

## 快速开始

```bash
git clone https://github.com/cxch51507202/index-tts-api.git
cd index-tts-api
conda create -n index-tts python=3.10
conda activate index-tts
conda install -c conda-forge ffmpeg pynini==2.1.6
pip install -e .
```

请先从 [pytorch.org](https://pytorch.org/get-started/locally/) 安装匹配 CUDA 的 PyTorch，然后将模型文件下载到 `checkpoints/`：

```bash
pip install -U huggingface_hub
huggingface-cli download IndexTeam/IndexTTS-1.5 \
  config.yaml bigvgan_discriminator.pth bigvgan_generator.pth \
  bpe.model dvae.pth gpt.pth unigram_12000.vocab \
  --local-dir checkpoints
```

也可以从 ModelScope 的 [IndexTeam/Index-TTS-1.5](https://modelscope.cn/models/IndexTeam/Index-TTS-1.5) 获取镜像。

使用获得授权的参考音频运行命令行推理：

```bash
indextts "大家好，这是一个测试。" \
  --voice reference_voice.wav \
  --model_dir checkpoints \
  --config checkpoints/config.yaml \
  --output output.wav
```

启动 WebUI：

```bash
pip install -e ".[webui]" --no-build-isolation
python webui.py
```

然后打开 `http://127.0.0.1:7860`。

## API 服务

启动本地 API 前请复制配置模板：

```bash
cp api_config.example.json api_config.json
cp voices.example.json voices.json
python -m api_server
```

`api_server/` 提供 API Key 鉴权、音色管理、队列式生成、任务轮询，以及兼容 OpenAI 的 `/v1/audio/speech` 接口。请求示例请参阅 [API_README.md](API_README.md)。请勿提交 `api_data/`、私人录音、生成音频或 API Key。

## 许可证与负责任使用

源码采用 [Apache License 2.0](LICENSE)。模型权重受单独的 [Index 模型许可证](INDEX_MODEL_LICENSE) 约束；下载、修改、部署或商业使用模型前请仔细阅读。商业用途须事先取得许可方书面授权。

仅在获得说话人知情同意的前提下进行音色复刻或语音合成。不得将本项目用于诈骗、冒充、骚扰、违法活动或违反适用法律的内容。

## 致谢

本仓库基于 bilibili Index 团队发布的原始 [IndexTTS](https://github.com/index-tts/index-tts) 项目，并感谢以下开源项目：

- [Tortoise TTS](https://github.com/neonbjb/tortoise-tts)
- [Coqui TTS / XTTSv2](https://github.com/coqui-ai/TTS)
- [NVIDIA BigVGAN](https://github.com/NVIDIA/BigVGAN)
- [WeNet](https://github.com/wenet-e2e/wenet)
- [Icefall](https://github.com/k2-fsa/icefall)
- [FastAPI](https://github.com/fastapi/fastapi)、[Uvicorn](https://github.com/Kludex/uvicorn) 和 [Gradio](https://github.com/gradio-app/gradio)

重新分发前请分别审阅上述各依赖项目的许可证。

## 论文与引用

评测方法和结果请参阅 [IndexTTS 论文](https://arxiv.org/abs/2502.05512)。

```bibtex
@article{deng2025indextts,
  title={IndexTTS: An Industrial-Level Controllable and Efficient Zero-Shot Text-To-Speech System},
  author={Wei Deng and Siyi Zhou and Jingchen Shu and Jinchao Wang and Lu Wang},
  journal={arXiv preprint arXiv:2502.05512},
  year={2025}
}
```
