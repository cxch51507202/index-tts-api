# IndexTTS 1.5

<div align="center">
  <img src="assets/index_icon.png" width="180" alt="IndexTTS" />
  <h2>Industrial-level controllable and efficient zero-shot text-to-speech</h2>
  <p>工业级可控、高效的零样本文本转语音系统</p>
</div>

<p align="center">
  <a href="https://arxiv.org/abs/2502.05512"><img src="https://img.shields.io/badge/arXiv-2502.05512-b31b1b" alt="Paper" /></a>
  <a href="https://github.com/index-tts/index-tts"><img src="https://img.shields.io/badge/upstream-index--tts-181717?logo=github" alt="Upstream" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/code-Apache--2.0-green" alt="Apache 2.0" /></a>
</p>

> **Notice / 说明**
>
> This repository is a community-maintained fork/workspace based on the upstream [IndexTTS](https://github.com/index-tts/index-tts) project. It contains source-code and integration changes; it does not redistribute model weights.
>
> 本仓库是基于上游 [IndexTTS](https://github.com/index-tts/index-tts) 的社区维护版本，包含源码和集成改动，不重新分发模型权重。

## English

IndexTTS is a GPT-style zero-shot TTS system for Chinese and English. Given a short reference recording, it can synthesize speech in the reference voice while preserving controllable pronunciation and prosody. IndexTTS 1.5 improves stability and English performance and includes an optional WebUI and a local FastAPI service in this fork.

### Highlights

- Zero-shot voice cloning from a short reference recording
- Chinese character-pinyin hybrid modeling for pronunciation correction
- Punctuation-aware pauses and controllable inference settings
- Conformer speaker conditioning and BigVGAN2-based decoding
- Command-line inference, Gradio WebUI, and optional queued API service

### Quick start

```bash
git clone <your-github-repository-url>
cd index-tts-1.5
conda create -n index-tts python=3.10
conda activate index-tts
conda install -c conda-forge ffmpeg pynini==2.1.6
pip install -e .
```

Install a CUDA-compatible PyTorch build from [pytorch.org](https://pytorch.org/get-started/locally/), then download the model files (the weights are not stored in Git):

```bash
pip install -U huggingface_hub
huggingface-cli download IndexTeam/IndexTTS-1.5 \
  config.yaml bigvgan_discriminator.pth bigvgan_generator.pth \
  bpe.model dvae.pth gpt.pth unigram_12000.vocab \
  --local-dir checkpoints
```

For users in China, `HF_ENDPOINT=https://hf-mirror.com` can be used when appropriate. ModelScope mirrors are available from [IndexTeam/Index-TTS-1.5](https://modelscope.cn/models/IndexTeam/Index-TTS-1.5).

Run CLI inference with a voice recording you are authorized to use:

```bash
indextts "Hello, this is a test." \
  --voice reference_voice.wav \
  --model_dir checkpoints \
  --config checkpoints/config.yaml \
  --output output.wav
```

Start the WebUI:

```bash
pip install -e ".[webui]" --no-build-isolation
python webui.py
```

Then open `http://127.0.0.1:7860`.

### Optional API service

The `api_server/` package provides API-key authentication, voice management, queued generation, task polling, and an OpenAI-compatible `/v1/audio/speech` endpoint. Copy the templates before running locally:

```bash
copy api_config.example.json api_config.json
copy voices.example.json voices.json
python -m api_server
```

See [API_README.md](API_README.md) for endpoint examples. Never commit `api_data/`, private recordings, generated audio, or API keys.

### License and responsible use

Source code is licensed under [Apache License 2.0](LICENSE). Model weights are governed by the separate [Index model license](INDEX_MODEL_LICENSE); review it before downloading, modifying, hosting, or using the model commercially. Commercial use requires prior written authorization from the licensor.

Only clone or synthesize voices with the speaker's informed consent. Do not use the system for fraud, impersonation, harassment, unlawful activity, or content that violates applicable law.

## 简体中文

IndexTTS 是面向中文和英文的 GPT 风格零样本文本转语音系统。提供一段较短的参考音频后，系统可以在保留音色特征的同时生成语音，并通过拼音、标点和推理参数控制发音与韵律。IndexTTS 1.5 进一步提升了稳定性和英文表现；本分支另外集成了可选的 WebUI 和本地 FastAPI 服务。

### 主要特性

- 使用短参考音频进行零样本音色复刻
- 字符-拼音混合建模，便于修正中文发音
- 根据标点控制停顿，支持多项推理参数调节
- Conformer 说话人条件编码器与 BigVGAN2 解码器
- 支持命令行、Gradio WebUI，以及可选的队列式 API 服务

### 快速开始

```bash
git clone <你的-GitHub-仓库地址>
cd index-tts-1.5
conda create -n index-tts python=3.10
conda activate index-tts
conda install -c conda-forge ffmpeg pynini==2.1.6
pip install -e .
```

请先从 [pytorch.org](https://pytorch.org/get-started/locally/) 安装匹配 CUDA 的 PyTorch，然后下载模型文件（模型权重不会存入 Git）：

```bash
pip install -U huggingface_hub
huggingface-cli download IndexTeam/IndexTTS-1.5 \
  config.yaml bigvgan_discriminator.pth bigvgan_generator.pth \
  bpe.model dvae.pth gpt.pth unigram_12000.vocab \
  --local-dir checkpoints
```

国内用户可按网络情况设置 `HF_ENDPOINT=https://hf-mirror.com`，也可以从 ModelScope 的 [IndexTeam/Index-TTS-1.5](https://modelscope.cn/models/IndexTeam/Index-TTS-1.5) 获取镜像。

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

### 可选 API 服务

`api_server/` 提供 API Key 鉴权、音色管理、队列式生成、任务轮询，以及兼容 OpenAI 的 `/v1/audio/speech` 接口。运行前请复制配置模板：

```bash
copy api_config.example.json api_config.json
copy voices.example.json voices.json
python -m api_server
```

接口示例见 [API_README.md](API_README.md)。请勿提交 `api_data/`、私人录音、生成音频或 API Key。

### 许可证与负责任使用

源码采用 [Apache License 2.0](LICENSE)。模型权重受单独的 [Index 模型许可证](INDEX_MODEL_LICENSE) 约束；下载、修改、部署或商业使用模型前请仔细阅读。商业用途须事先取得许可方书面授权。

仅在获得说话人知情同意的前提下进行音色复刻或语音合成。不得将本项目用于诈骗、冒充、骚扰、违法活动或违反适用法律的内容。

## Acknowledgements / 致谢

This repository builds on the original [IndexTTS](https://github.com/index-tts/index-tts) project by bilibili Index. The upstream project credits the following open-source projects, which are also relevant to this fork:

- [Tortoise TTS](https://github.com/neonbjb/tortoise-tts): GPT-style text-to-speech research and implementation foundations.
- [Coqui TTS / XTTSv2](https://github.com/coqui-ai/TTS): zero-shot TTS architecture and related components.
- [NVIDIA BigVGAN](https://github.com/NVIDIA/BigVGAN): neural vocoder and audio-generation components.
- [WeNet](https://github.com/wenet-e2e/wenet): speech-recognition and speech-processing components.
- [Icefall](https://github.com/k2-fsa/icefall): speech-recognition recipes and supporting tooling.
- [FastAPI](https://github.com/fastapi/fastapi), [Uvicorn](https://github.com/Kludex/uvicorn), and [Gradio](https://github.com/gradio-app/gradio): the optional API and WebUI layers included in this fork.

本仓库基于 bilibili Index 团队发布的原始 [IndexTTS](https://github.com/index-tts/index-tts) 项目。上游项目致谢并依赖以下开源项目，本分支同样受益于这些工作：

- [Tortoise TTS](https://github.com/neonbjb/tortoise-tts)：GPT 风格文本转语音研究与实现基础。
- [Coqui TTS / XTTSv2](https://github.com/coqui-ai/TTS)：零样本文本转语音架构及相关组件。
- [NVIDIA BigVGAN](https://github.com/NVIDIA/BigVGAN)：神经声码器与音频生成组件。
- [WeNet](https://github.com/wenet-e2e/wenet)：语音识别与语音处理组件。
- [Icefall](https://github.com/k2-fsa/icefall)：语音识别方案与辅助工具。
- [FastAPI](https://github.com/fastapi/fastapi)、[Uvicorn](https://github.com/Kludex/uvicorn) 和 [Gradio](https://github.com/gradio-app/gradio)：本分支集成的可选 API 与 WebUI 层。

Please review the licenses of all dependencies before redistribution.
重新分发前请分别审阅上述各依赖项目的许可证。

## Paper and citation / 论文与引用

See the [IndexTTS paper](https://arxiv.org/abs/2502.05512) for benchmark methodology and results.
评测方法和结果请参阅 [IndexTTS 论文](https://arxiv.org/abs/2502.05512)。

```bibtex
@article{deng2025indextts,
  title={IndexTTS: An Industrial-Level Controllable and Efficient Zero-Shot Text-To-Speech System},
  author={Wei Deng and Siyi Zhou and Jingchen Shu and Jinchao Wang and Lu Wang},
  journal={arXiv preprint arXiv:2502.05512},
  year={2025}
}
```
