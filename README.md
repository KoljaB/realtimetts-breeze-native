# realtimetts-breeze-native

This repository distributes the pinned Vulkan Breeze worker used by RealtimeTTS.
The wheel includes a shell-free launcher, native build provenance, and
third-party notices. End users install a platform wheel; they do not need a
C++ compiler, CMake, Vulkan SDK, or local native build.

0.1.0 is the first final release on PyPI. Release wheels are built by CI
from a tagged commit on `main` and published with `tools/release.py`, which checks
their build-info against `build_package.py`. Model weights, credentials, GPU drivers,
and vendor ICDs are never included.

CI attests every wheel and sdist it builds (GitHub build provenance), and the
release uploads those files unchanged. Releases after 0.1.0rc8 can be checked
with the [GitHub CLI](https://cli.github.com/):

```bash
gh attestation verify <file> --repo KoljaB/realtimetts-breeze-native
```

## Supported targets

The first candidate targets Windows x64 (win_amd64) and Linux x64. Linux
wheels are built on Ubuntu 22.04 and repaired to manylinux_2_35_x86_64 after
auditwheel inspection. macOS and ARM wheels are outside this package contract.

The worker uses the patched control path, Vulkan, and static Breeze/ggml
components. MP3, CUDA, CLI, tests, and GGML_NATIVE are disabled. The tested
model contract is the official Q8_0 model; Breeze model use remains subject
to its research and non-commercial licence. A host Vulkan loader, driver, and
ICD are required. Windows build output DLLs beside the worker are copied and
hashed in build-info.json, except the system Vulkan loader. Linux auditwheel
may vendor an ELF loader dependency; release evidence records the actual
show and repair output.

## Install and run on Windows or Linux

The end-user preview is installed from **TestPyPI** with **uv**. A compiler,
Git checkout and local wheel files are unnecessary. After the preview is published:

~~~bat
uv venv --python 3.11 .venv-breeze
uv pip install --python .venv-breeze --find-links https://test.pypi.org/simple/realtimetts/ --find-links https://test.pypi.org/simple/realtimetts-breeze-native/ "realtimetts[breeze-server]==0.9.0rc23"
uv run --no-project --python .venv-breeze python -m RealtimeTTS.breeze_server --reference-prefix-cache --port 18086
~~~

Open **http://127.0.0.1:18086/studio** after warmup and select a bundled voice.
First startup downloads the pinned 3.6 GB Q8_0 model ;
later starts reuse cached assets. RealtimeTTS starts and stops the native worker.

The [complete Windows guide](docs/windows-server-preview.md) also provides
Qwen CPU/GPU setup, readiness checks and a tiny Python streaming client.

To install only the worker:

~~~bat
uv pip install --python .venv-breeze "realtimetts-breeze-native==0.1.0"
uv run --no-project --python .venv-breeze python -c "from realtimetts_breeze_native import executable_path; print(executable_path())"
~~~

On Linux x86-64 with an NVIDIA GPU, the separate CUDA 12 worker is faster
(`realtimetts-breeze-native-cuda12==0.1.0`, or `realtimetts[breeze-server,breeze-cuda]`).
It needs only the NVIDIA driver; the CUDA runtime and cuBLAS come from NVIDIA's wheels.

The native package does not download weights. Model caching and
`--download-model` belong to RealtimeTTS.

## Maintainer build

build_native.py clones the exact upstream revision, initializes its exact
ggml submodule, applies tools/breeze_cpp_controls.json, configures CMake,
builds breeze-server, stages provenance, and creates an sdist plus platform
wheel. Source, build, and stage directories default outside this checkout.

Linux CI downloads and verifies LunarG Vulkan SDK 1.3.296.0 through the official
versioned endpoint, then repairs the wheel with auditwheel. Windows CI uses
Winlibs GCC 12.2.0 and MSYS2 shaderc 2026.3, glslang 16.3.0 and Vulkan 1.4.357.0.
The exact archive names and SHA-256 hashes are pinned in
tools/install_windows_toolchain.py. These reproduce the working Windows compiler
and shader tools while keeping GGML_NATIVE=OFF. See .github/workflows/ci.yml for
the complete reproducible build commands. Users of the wheels need neither SDK
nor compiler.

Use --source-dir only for a clean checkout at the pinned revision. The lower
level build_package.py assembler accepts only a completed Release CMake build,
the exact controls patch, and an empty stage outside this repository.

## Pinned inputs

- Breeze-TTS-2.cpp: main after v0.1.7, 155e60818433ea6322367aff8f8436ba790f6fbe (2026-11-15)
- ggml: 36da57138425487184aa1da2eee2cde155909c6f
- SPIRV-Headers (vulkan-sdk-1.3.296.0): 2a9b6f951c7d6b04b6c21fe1bf3f475b68b84801
- controls SHA-256: 95c3655729108977dcba75a5fc71252ea7169d54cba67bef2af888651963de49 (0.1.0; rc8: bfba1d16…9831, rc7: 4e9f771e…5b79, rc4: 12c938d1…25e9b3)

Read bundled notices before redistribution. The model licence is separate from
the package licence.

## Breeze main after v0.1.7 (0.1.0)

0.1.0 moves the pinned source from v0.1.6 to upstream main 155e608 (v0.1.7 plus
the 2026-11-10 and 2026-11-15 commits). ggml is unchanged. New upstream options,
all off by default:

- `BREEZE_TE_EMBED_CPU=1` (environment) keeps the text encoder's word table in
  system memory, about 300 MB less video memory. Upstream measured identical audio
  and unchanged first audio.
- `--te-cpu` runs the whole text encoder on the CPU, about 1 GB less video memory,
  but upstream measured about 0.7 s more before each piece of text.
- `--idle-unload SECONDS`, `--lazy` and `--before-load CMD`, plus `POST /v1/unload`
  and `POST /v1/load`: the model can leave the GPU while nothing generates, and the
  next request loads it back first. `/health` adds `loaded`, `busy` and `idle_seconds`.
- `--talk` serves upstream's voice call demo at `/talk` (needs tyger-server and an LLM).

The controls are re-anchored to the new scheduler API. With the model off the GPU,
prewake passes are skipped (a prewake does not load the model), a synthesis or voice
registration loads it back first, and one that cannot load it gets an `error` event
or HTTP 503. `/health` keeps the RealtimeTTS capability fields next to the new ones;
its `backend` name is read once at startup.

## Breeze v0.1.6 (0.1.0rc8)

rc8 moves the pinned source from a0e177f (September) to upstream v0.1.6:

- The vocoder keeps its state between flushes and decodes only new frames, and it
  upsamples with a matmul. Upstream measures about 6.6 -> 2.4 ms per frame on Vulkan.
- The depth decoder runs all codebooks and their sampling in one GPU graph,
  about 30% faster per frame.
- The first chunk sizes itself. `--chunk-first` is a floor: the worker starts with
  1 frame when the GPU keeps well ahead of playback, and 2, 4 or 8 when it does not.
  Later flushes go out early when the listener is about to run dry.
- The CUDA build turns on CUDA graphs (`GGML_CUDA_GRAPHS`).
- `--parallel N` lets streams share one GPU batch per frame. The default stays 1.
- Every request runs on one GPU thread (the upstream scheduler). The controls now
  live there too: stop and pause are polled between frames instead of blocking, a
  paused stream holds its slot and takes no frames, and the `paused` event follows
  the audio already sent. The reference-prefix cache is lent to one stream at a time,
  and a second stream in the same batch prefills in full.
- The rc3 second-chunk rule is gone; the upstream ramp and early flush replace it.
- Upstream now embeds the WebUI as byte arrays, so the bounded embed script this
  package used to install is no longer needed.

## GPU prewake (0.1.0rc7, first released in 0.1.0rc8)

The controls add an opt-in `prewake` stream message, sent before the first text:
the worker runs 4-frame vocoder passes on silent codes, the size of the first real
chunk, until text arrives, the stream is cancelled or closed, or `max_ms` passes
(default 1500, maximum 5000). Since rc8 each pass runs on the GPU thread only while no
stream is queued or generating, so it never delays speech on any connection. It ends with a `prewake_done` event, and `/health` reports
`gpu_prewake`. It keeps an idle Windows GPU from starting a reply at idle clocks
(RealtimeTTS and Miep use it only when the server advertises it).

Voice registration waits for the GPU (up to 2 s) instead of answering 409 at once,
and prewake passes skip the GPU while it waits. In rc5 the back-to-back passes
made registrations fail with 409 while the user paused.

A synthesis that has to wait for the GPU counts as a waiter too, so a prewake on
another connection stops taking the GPU. In rc6 such a synthesis waited behind the
whole prewake (measured: 1281 ms to first PCM, against 281 ms on the woken
connection and 563 ms with no prewake).

## CUDA 12 worker (0.1.0rc4)

0.1.0rc4 rebuilds the unchanged rc3 source and control patch and adds
`realtimetts-breeze-native-cuda12` for Linux x86-64: the same worker built with
CUDA for architectures 86, 89, 90 and 120 (machine code for each, PTX for 120).
On an RTX 4090 it reached the first audible sample about 35 ms sooner than the
Vulkan worker. Both packages come from one tagged commit and CI run.

## Early streaming cadence (0.1.0rc3)

The second chunk stays small before resuming the existing ramp.
With the default first4/max6 profile this produces 4, 4, 6, 6 frames. The first
chunk and steady-state chunk size are unchanged; the second chunk arrives earlier
to preserve headroom when pitch-preserving tempo processing retains some audio.
No playback buffer is added. Native per-request timings remain in WebSocket
metrics; redundant console writes no longer block completion and the tempo tail.

## Portable performance build (0.1.0rc2)

Both platform wheels include the reference-prefix cache, bounded cross-sentence
context, cache invalidation and native timing metrics from the working runtime.
These are shared source changes; GGML_NATIVE stays OFF. No machine-specific CPU
affinity masks, thread counts or GPU device IDs are embedded in the wheels.
Enable the reference-prefix cache through the RealtimeTTS Python server option
--reference-prefix-cache. Vulkan drivers remain a host requirement.
