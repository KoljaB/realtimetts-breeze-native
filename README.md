# realtimetts-breeze-native

This repository distributes the pinned Vulkan Breeze worker used by RealtimeTTS.
The wheel includes a shell-free launcher, native build provenance, and
third-party notices. End users install a platform wheel; they do not need a
C++ compiler, CMake, Vulkan SDK, or local native build.

The 0.1.0rc2 package is a TestPyPI candidate. Release wheels are verified
against their exact installed runtime artifacts before publication. Model weights, credentials, GPU drivers,
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

## Install and run on Windows or Linux

The end-user preview is installed from **TestPyPI** with **uv**. A compiler,
Git checkout and local wheel files are unnecessary. After the preview is published:

~~~bat
uv venv --python 3.11 .venv-breeze
uv pip install --python .venv-breeze --find-links https://test.pypi.org/simple/realtimetts/ --find-links https://test.pypi.org/simple/realtimetts-breeze-native/ "realtimetts[breeze-server]==0.9.0rc4"
uv run --no-project --python .venv-breeze python -m RealtimeTTS.breeze_server --reference-prefix-cache --port 18086
~~~

Open **http://127.0.0.1:18086/studio** after warmup and select a bundled voice.
First startup downloads the pinned 3.6 GB Q8_0 model ;
later starts reuse cached assets. RealtimeTTS starts and stops the native worker.

The [complete Windows guide](docs/windows-server-preview.md) also provides
Qwen CPU/GPU setup, readiness checks and a tiny Python streaming client.

To install only the worker:

~~~bat
uv pip install --python .venv-breeze --find-links https://test.pypi.org/simple/realtimetts-breeze-native/ "realtimetts-breeze-native==0.1.0rc2"
uv run --no-project --python .venv-breeze python -c "from realtimetts_breeze_native import executable_path; print(executable_path())"
~~~

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

The build replaces the pinned upstream WebUI embed script with
tools/embed_webui.cmake. It keeps the WebUI files byte-for-byte unchanged while
splitting each generated C++ raw literal into bounded chunks, avoiding MSVC
C2026 without changing the served assets or WebUI capability.

## Pinned inputs

- Breeze-TTS-2.cpp: a0e177f91242ebbd2ea8d61548d742c89e4b9e06
- ggml: 36da57138425487184aa1da2eee2cde155909c6f
- SPIRV-Headers (vulkan-sdk-1.3.296.0): 2a9b6f951c7d6b04b6c21fe1bf3f475b68b84801
- controls SHA-256: 5d4e5e3b69c0fa1f81bb4d291b78764270c6dbb18656e2a4ce4bce9f2dbabf4e

Read bundled notices before redistribution. The model licence is separate from
the package licence.

## Portable performance build (0.1.0rc2)

Both platform wheels include the reference-prefix cache, bounded cross-sentence
context, cache invalidation and native timing metrics from the working runtime.
These are shared source changes; GGML_NATIVE stays OFF. No machine-specific CPU
affinity masks, thread counts or GPU device IDs are embedded in the wheels.
Enable the reference-prefix cache through the RealtimeTTS Python server option
--reference-prefix-cache. Vulkan drivers remain a host requirement.
