#!/usr/bin/env bash
set -euo pipefail

APP_NAME="gbccs"
OUT_DIR_REL="installers/mac/installer_out"
SPEC_REL="installers/mac/gbccs.mac.spec"
CLEAN_BUILD_DIR="${CLEAN_BUILD_DIR:-1}"
TARGET_ARCH="${TARGET_ARCH:-}"
MACOS_BUNDLE_ID="${MACOS_BUNDLE_ID:-edu.iastate.gbccs}"
APP_VERSION="${APP_VERSION:-}"
BUILD_PYTHON="${BUILD_PYTHON:-}"
SKIP_UV_SYNC="${SKIP_UV_SYNC:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
OUT_DIR="${REPO_ROOT}/${OUT_DIR_REL}"
SPEC_PATH="${REPO_ROOT}/${SPEC_REL}"
APP_PATH="${REPO_ROOT}/dist/${APP_NAME}.app"
APP_PLIST="${APP_PATH}/Contents/Info.plist"

normalize_arch() {
  case "${1:-}" in
    arm64|aarch64) echo "arm64" ;;
    x86_64|amd64) echo "x86_64" ;;
    *) echo "${1:-}" ;;
  esac
}

run_python() {
  if [[ -n "${BUILD_PYTHON}" ]]; then
    "${BUILD_PYTHON}" "$@"
  else
    uv run python "$@"
  fi
}

run_pyinstaller() {
  if [[ -n "${BUILD_PYTHON}" ]]; then
    "${BUILD_PYTHON}" -m PyInstaller "$@"
  else
    uv run pyinstaller "$@"
  fi
}

echo "== cd to repo root =="
cd "${REPO_ROOT}"

if [[ "${SKIP_UV_SYNC}" != "1" ]]; then
  echo "== sync deps (uv) =="
  uv sync
fi

if [[ -z "${TARGET_ARCH}" ]]; then
  TARGET_ARCH="$(run_python - <<'PY'
import platform
machine = platform.machine().strip().lower()
if machine in {"arm64", "aarch64"}:
    print("arm64")
elif machine in {"x86_64", "amd64"}:
    print("x86_64")
else:
    raise SystemExit(f"Unsupported python architecture: {machine}")
PY
)"
fi

case "${TARGET_ARCH}" in
  arm64|x86_64) ;;
  *)
    echo "ERROR: TARGET_ARCH must be arm64 or x86_64 (got '${TARGET_ARCH}')"
    exit 1
    ;;
esac

if [[ -z "${APP_VERSION}" ]]; then
  APP_VERSION="$(run_python - <<'PY'
import tomllib
with open("pyproject.toml", "rb") as fh:
    print(str(tomllib.load(fh).get("project", {}).get("version", "0.1.0")))
PY
)"
fi

PYTHON_ARCH="$(run_python - <<'PY'
import platform
machine = platform.machine().strip().lower()
if machine in {"arm64", "aarch64"}:
    print("arm64")
elif machine in {"x86_64", "amd64"}:
    print("x86_64")
else:
    print(machine)
PY
)"

if [[ "${PYTHON_ARCH}" != "${TARGET_ARCH}" ]]; then
  echo "ERROR: Python environment architecture (${PYTHON_ARCH}) does not match TARGET_ARCH (${TARGET_ARCH})."
  exit 1
fi

echo "== verify native module architectures for ${TARGET_ARCH} =="
BINARY_PATHS=()
NATIVE_PATHS_FILE="$(mktemp)"
run_python - <<'PY' > "${NATIVE_PATHS_FILE}"
import importlib
from pathlib import Path


def resolve_binary(module_name: str) -> str:
    mod = importlib.import_module(module_name)
    module_path = Path(mod.__file__).resolve()
    if module_path.suffix in {".so", ".dylib"}:
        return str(module_path)

    package_dir = module_path.parent
    candidates = sorted(
        path for path in package_dir.iterdir()
        if path.is_file() and path.suffix in {".so", ".dylib"}
    )
    if not candidates:
        raise RuntimeError(f"No native binary found for {module_name} in {package_dir}")
    return str(candidates[0])


mods = [
    "cv2",
    "numpy._core._multiarray_umath",
    "mediapipe.python._framework_bindings",
    "autopy",
    "PySide6.QtCore",
]
for name in mods:
    print(resolve_binary(name))
PY

while IFS= read -r binary_path; do
  BINARY_PATHS+=("${binary_path}")
done < "${NATIVE_PATHS_FILE}"
rm -f "${NATIVE_PATHS_FILE}"

if [[ ${#BINARY_PATHS[@]} -eq 0 ]]; then
  echo "ERROR: failed to resolve native module paths for architecture verification"
  exit 1
fi

for binary_path in "${BINARY_PATHS[@]}"; do
  [[ -n "${binary_path}" ]] || continue
  echo "-- ${binary_path}"
  file_output="$(file "${binary_path}")"
  echo "   ${file_output}"
  if [[ "${file_output}" == *"universal binary"* ]]; then
    if [[ "${file_output}" != *"${TARGET_ARCH}"* ]]; then
      echo "ERROR: ${binary_path} does not contain ${TARGET_ARCH}"
      exit 1
    fi
  elif [[ "${file_output}" != *"${TARGET_ARCH}"* ]]; then
    echo "ERROR: ${binary_path} is not built for ${TARGET_ARCH}"
    exit 1
  fi
done

echo "== clean old outputs =="
rm -rf build dist
mkdir -p "${OUT_DIR}"

if [[ ! -f "${SPEC_PATH}" ]]; then
  echo "ERROR: mac spec not found at ${SPEC_PATH}"
  exit 1
fi

echo "== build app bundle using mac spec =="
GBCCS_REPO_ROOT="${REPO_ROOT}" GBCCS_MAC_SPEC_DIR="${SCRIPT_DIR}" \
MACOS_BUNDLE_ID="${MACOS_BUNDLE_ID}" APP_VERSION="${APP_VERSION}" TARGET_ARCH="${TARGET_ARCH}" \
  run_pyinstaller --noconfirm "${SPEC_PATH}"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "ERROR: expected ${APP_PATH} not found"
  exit 1
fi

if [[ ! -f "${APP_PLIST}" ]]; then
  echo "ERROR: expected ${APP_PLIST} not found"
  exit 1
fi

echo "== validate Info.plist =="
plutil -p "${APP_PLIST}"
CAMERA_USAGE="$(/usr/libexec/PlistBuddy -c "Print :NSCameraUsageDescription" "${APP_PLIST}" 2>/dev/null || true)"
if [[ -z "${CAMERA_USAGE}" ]]; then
  echo "ERROR: NSCameraUsageDescription missing from ${APP_PLIST}"
  exit 1
fi

echo "== validate code signature =="
codesign -dv --verbose=4 "${APP_PATH}" 2>&1
codesign --verify --deep --strict "${APP_PATH}"

echo "== check Gatekeeper assessment =="
SPCTL_OUTPUT="$(spctl -a -vv "${APP_PATH}" 2>&1 || true)"
echo "${SPCTL_OUTPUT}"
if echo "${SPCTL_OUTPUT}" | grep -qi "invalid"; then
  echo "ERROR: spctl reported an invalid app bundle"
  exit 1
fi

echo "== build DMG =="
DMG_PATH="${OUT_DIR}/${APP_NAME}-macos-${TARGET_ARCH}.dmg"
TEMP_DMG="${OUT_DIR}/${APP_NAME}-macos-${TARGET_ARCH}-temp.dmg"
STAGE_DIR="${OUT_DIR}/dmg_stage_${TARGET_ARCH}"

rm -f "${DMG_PATH}" "${TEMP_DMG}"
rm -rf "${STAGE_DIR}"
mkdir -p "${STAGE_DIR}"

cp -R "${APP_PATH}" "${STAGE_DIR}/"
ln -s /Applications "${STAGE_DIR}/Applications"

hdiutil create -volname "${APP_NAME}" -srcfolder "${STAGE_DIR}" -ov -format UDRW "${TEMP_DMG}" >/dev/null
hdiutil convert "${TEMP_DMG}" -format UDZO -o "${DMG_PATH}" >/dev/null

rm -f "${TEMP_DMG}"
rm -rf "${STAGE_DIR}"

if [[ "${CLEAN_BUILD_DIR}" == "1" ]]; then
  echo "== cleanup: removing build/ =="
  rm -rf build
fi

echo ""
echo "DONE."
echo "App: ${APP_PATH}"
echo "DMG: ${DMG_PATH}"
echo "Bundle ID: ${MACOS_BUNDLE_ID}"
echo "Version: ${APP_VERSION}"
