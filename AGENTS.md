# RealtimeTTS Breeze native package

Keep pinned native revisions, controls, CMake flags, provenance, and host Vulkan requirements explicit. Model weights, credentials, and drivers do not belong here.

## Releases

Release wheels (`realtimetts-breeze-native` and `realtimetts-breeze-native-cuda12`) come from GitHub CI, never from a local build.

1. Merge the release state into `main` (fast-forward), tag it `v<version>`, and push both.
2. Wait for the CI run of that commit to succeed and download its wheel and sdist artifacts unchanged.
3. Install the CI wheel and smoke-test the worker on its target GPU (Linux: Vulkan and CUDA; Windows: Vulkan).
4. Publish only with `python tools/release.py publish --repository testpypi --ci-run <run id> <artifacts>`. It refuses a dirty tree, an untagged or unpushed commit, a commit not on `main`, artifacts from another CI run, build-info that differs from `build_package.py`, and failed `twine check`; after uploading it compares the index SHA-256 values with the local files.

Never upload directly with Twine, never replace files under an existing version, and keep `tools/release.py` identical to the copy in the RealtimeTTS repository.
