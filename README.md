# realtimetts-breeze-native

This repository distributes the pinned Vulkan Breeze worker used by RealtimeTTS.
The wheel includes a shell-free launcher, native build provenance, and
third-party notices. End users install a platform wheel; they do not need a
C++ compiler, CMake, Vulkan SDK, or local native build.

The 0.1.0.dev1 package is a TestPyPI candidate. Publication is performed by
the RealtimeTTS release guard after clean-commit, exact-artifact, runtime
parity, and signed-attestation checks. Model weights, credentials, GPU drivers,
and vendor ICDs are never included.

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

## Install and run from CMD.exe

The end-user preview is installed from **TestPyPI** with **uv**. A compiler,
Git checkout and local wheel files are unnecessary. After the preview is published:

~~~bat
uv venv --python 3.11 .venv-breeze
uv pip install --python .venv-breeze\Scripts\python.exe --find-links https://test.pypi.org/simple/realtimetts/ --find-links https://test.pypi.org/simple/realtimetts-breeze-native/ "realtimetts[breeze-server]==1.0.0.dev2"
.venv-breeze\Scripts\realtimetts-breeze-server.exe --download-model --demo-voice --port 18086
~~~

Open **http://127.0.0.1:18086/studio** after warmup and select **demo-neutral**.
First startup downloads the pinned 3.6 GB Q8_0 model and the public reference;
later starts reuse cached assets. RealtimeTTS starts and stops the native worker.

The [complete Windows guide](docs/windows-server-preview.md) also provides
Qwen CPU/GPU setup, readiness checks and a tiny Python streaming client.

To install only the worker:

~~~bat
uv pip install --python .venv-breeze\Scripts\python.exe --find-links https://test.pypi.org/simple/realtimetts-breeze-native/ "realtimetts-breeze-native==0.1.0.dev1"
.venv-breeze\Scripts\python.exe -c "from realtimetts_breeze_native import executable_path; print(executable_path())"
~~~

The native package does not download weights. Model caching and
`--download-model` belong to RealtimeTTS.

## Maintainer build

build_native.py clones the exact upstream revision, initializes its exact
ggml submodule, applies tools/breeze_cpp_controls.json, configures CMake,
builds breeze-server, stages provenance, and creates an sdist plus platform
wheel. Source, build, and stage directories default outside this checkout.

Windows CI downloads and verifies LunarG Vulkan SDK 1.3.296.0 with SHA-256
acb4ae0786fd3e558f8b3c36cc3eba91638984217ba8a6795ec64d2f9ffd8c4b, then
runs the official installer in copy-only mode. Linux CI installs the Ubuntu
Vulkan development package and runs auditwheel repair.

~~~
py -3.12 -m pip install build pytest
py -3.12 build_native.py --platform win_amd64 --generator "Visual Studio 17 2022"
~~~

Use --source-dir only for a clean checkout at the pinned revision. The lower
level build_package.py assembler accepts only a completed Release CMake build,
the exact controls patch, and an empty stage outside this repository.

## Pinned inputs

- Breeze-TTS-2.cpp: a0e177f91242ebbd2ea8d61548d742c89e4b9e06
- ggml: 36da57138425487184aa1da2eee2cde155909c6f
- controls SHA-256: 990b37b0d56047ae0bbe85b14709f7b094a070f825599e991a95d0eb1f6d2e6a

Read bundled notices before redistribution. The model licence is separate from
the package licence.
