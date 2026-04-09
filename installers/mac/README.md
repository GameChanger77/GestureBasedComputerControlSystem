Build macOS installers from `installers/mac` or the repo root.

## Outputs
- `installers/mac/installer_out/gbccs-macos-arm64.dmg`
- `installers/mac/installer_out/gbccs-macos-x86_64.dmg`

## Build Apple Silicon
```bash
TARGET_ARCH=arm64 ./installers/mac/build_mac.sh
```

## Build Intel
```bash
TARGET_ARCH=x86_64 ./installers/mac/build_mac.sh
```

## Build Intel On Apple Silicon Under Rosetta
```bash
arch -x86_64 /usr/local/bin/python3.11 -m venv .venv-macos-x86_64
uv export --format requirements.txt --no-hashes --frozen --all-groups --no-emit-project -o /tmp/gbccs-x86-requirements.txt
grep -Ev '^(jax|jaxlib)==' /tmp/gbccs-x86-requirements.txt > /tmp/gbccs-x86-requirements-nojax.txt
arch -x86_64 .venv-macos-x86_64/bin/python -m pip install --upgrade pip setuptools wheel
arch -x86_64 .venv-macos-x86_64/bin/python -m pip install --no-deps -r /tmp/gbccs-x86-requirements-nojax.txt
arch -x86_64 env BUILD_PYTHON="$PWD/.venv-macos-x86_64/bin/python" SKIP_UV_SYNC=1 TARGET_ARCH=x86_64 ./installers/mac/build_mac.sh
```

## Notes
- The build environment must match `TARGET_ARCH`.
- Intel builds require an `x86_64` Python environment with `x86_64` native wheels.
- Apple Silicon builds require an `arm64` Python environment with `arm64` native wheels.
- The script verifies native extension architectures before packaging and will fail early on a mismatch.
- The app bundle carries `NSCameraUsageDescription` inside the signed bundle definition; the script does not edit `Info.plist` after build.
- `BUILD_PYTHON` can point the build script at a separate Python/PyInstaller environment, and `SKIP_UV_SYNC=1` skips syncing the default project environment when using that external interpreter.
- The current dependency set includes `jax` and `jaxlib`, but `jaxlib==0.8.0` does not ship a macOS `x86_64` wheel. The Rosetta flow above omits those two packages because they are not imported by the application.

## Install
1. Open the generated DMG.
2. Drag `gbccs.app` into `Applications`.
3. Eject the mounted disk image.

## First launch on macOS
- The app will request camera permission the first time tracking starts.
- If camera access is denied, enable it in `System Settings > Privacy & Security > Camera`.
- These builds are local distribution artifacts and are not notarized in this phase, so Gatekeeper may still require the standard “Open Anyway” flow.
