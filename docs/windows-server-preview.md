# Windows server preview

These commands use **CMD.exe**, [uv](https://docs.astral.sh/uv/getting-started/installation/),
and Python 3.11 installed automatically by uv. Run each server in its own terminal.
RealtimeTTS **1.0.0.dev2** and the Breeze native worker **0.1.0.dev1** come from
TestPyPI. Other dependencies come from normal PyPI.

Choose one server below. First startup downloads the model and public
`demo-neutral` reference, then warms synthesis before `/ready` succeeds.
Leave the terminal open. Later starts reuse the cache.

## Breeze GPU

Windows x64 with AVX2 and a working Vulkan GPU driver is required.
No compiler, PyTorch or CUDA toolkit is needed. The Q8_0 model download is 3.6 GB;
allow additional RAM/VRAM for inference.

```bat
uv venv --python 3.11 .venv-breeze
uv pip install --python .venv-breeze\Scripts\python.exe --find-links https://test.pypi.org/simple/realtimetts/ --find-links https://test.pypi.org/simple/realtimetts-breeze-native/ "realtimetts[breeze-server]==1.0.0.dev2"
.venv-breeze\Scripts\realtimetts-breeze-server.exe --download-model --demo-voice --port 18086
```

Open **http://127.0.0.1:18086/studio**, select **demo-neutral**, enter English or
Mandarin text and synthesize. The native worker starts and stops with this server.
To use a previously downloaded model, replace `--download-model` with
`--model "C:\models\breeze-tts-2-q8_0.gguf"`.
Add `--local-files-only` when both the model and demo voice are cached.

**Breeze's model and self-hosted outputs are for research and non-commercial use.
Commercial use needs a separate licence.** See the
[model licence](https://huggingface.co/BreezeBlue/Breeze-TTS-2/blob/main/LICENSE).
The independently packaged worker is maintained in
[realtimetts-breeze-native](https://github.com/KoljaB/realtimetts-breeze-native).

## Qwen CPU

Windows x64; no GPU required. CPU synthesis can be slower than playback,
depending on the processor and text. Start with the portable defaults before
tuning core/thread allocation.

```bat
uv venv --python 3.11 .venv-cpu
uv pip install --python .venv-cpu\Scripts\python.exe --find-links https://test.pypi.org/simple/realtimetts/ "realtimetts[qwen-cpu-server]==1.0.0.dev2"
.venv-cpu\Scripts\realtimetts-qwen-server.exe --device cpu --demo-voice --port 18084
```

Open **http://127.0.0.1:18084/studio**. The demo voice works with English,
Spanish and the other languages supported by Qwen3-TTS.

## Qwen GPU

Windows x64 with a supported NVIDIA GPU/driver. The native wheel includes its
CUDA runtime dependencies; a compiler and local CUDA toolkit are unnecessary.

```bat
uv venv --python 3.11 .venv-gpu
uv pip install --python .venv-gpu\Scripts\python.exe --find-links https://test.pypi.org/simple/realtimetts/ "realtimetts[qwen-server]==1.0.0.dev2"
.venv-gpu\Scripts\realtimetts-qwen-server.exe --device gpu --clone-mode speaker_only --demo-voice --port 18085
```

Open **http://127.0.0.1:18085/studio**. Use one GPU server at a time if there is
not enough VRAM for both models.

## Check readiness

In another CMD window:

```bat
curl.exe --fail http://127.0.0.1:18086/ready
```

Change the port to 18084 for Qwen CPU or 18085 for Qwen GPU.
A non-ready response during model loading or warmup is expected; retry after
the server reports readiness.

## Stream speech from Python

Create a lightweight client environment, also using the preview from TestPyPI:

```bat
uv venv --python 3.11 .venv-client
uv pip install --python .venv-client\Scripts\python.exe --find-links https://test.pypi.org/simple/realtimetts/ "realtimetts[routing,playback]==1.0.0.dev2"
```

Save this as `say.py`:

```python
from RealtimeTTS import RemoteTTSEngine, TextToAudioStream

engine = RemoteTTSEngine("http://127.0.0.1:18086", voice="demo-neutral", language="en")
stream = TextToAudioStream(engine)
try:
    stream.feed("Hello! This speech is streamed while it is generated.").play()
finally:
    stream.close()
```

Run `.venv-client\Scripts\python.exe say.py`.
For Qwen, change only the port. Audio starts from streamed PCM while the server
continues generating. The client needs an available audio output device.
The repository also includes `examples/remote_server_client.py` with URL,
voice, language and text arguments.

## Troubleshooting

- **No matching distribution:** use Windows x64/Python 3.11 and copy the exact
  version and both Breeze find-links options. This preview does not provide a
  Breeze macOS or Windows ARM wheel.
- **Breeze worker fails to initialize Vulkan:** install/update the GPU vendor's
  Vulkan-capable driver. The server rejects a CPU fallback.
- **Cannot reach server:** wait for warmup, keep its terminal open and check the
  port. These commands bind to localhost; they do not expose the API to a LAN.
- **Missing voice:** start with `--demo-voice` and choose `demo-neutral`.
  Upload personal references through Studio with their exact transcripts.
- **First request is slow:** model loading, initial shaders and warmup are cold
  costs; later requests reuse the loaded model.
