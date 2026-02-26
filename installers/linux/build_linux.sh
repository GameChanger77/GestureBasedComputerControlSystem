#!/usr/bin/env bash
set -euo pipefail

# ---------------- config ----------------
APP_NAME="gbccs"
ENTRY="main.py"
ICON_PNG_REL="installers/linux/${APP_NAME}_icon.png"

# Tools & Output
TOOLS_DIR_REL="installers/linux/tools"
OUT_DIR_REL="installers/linux/out"
APPDIR_REL="installers/linux/AppDir"
CLEAN_BUILD_DIR=1  # set to 0 to keep build/

# appimagetool download
APPIMAGETOOL_URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
APPIMAGETOOL_NAME="appimagetool-x86_64.AppImage"
# ----------------------------------------

# Resolve repo root (directory containing this script -> ../../)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

TOOLS_DIR="${REPO_ROOT}/${TOOLS_DIR_REL}"
OUT_DIR="${REPO_ROOT}/${OUT_DIR_REL}"
APPDIR="${REPO_ROOT}/${APPDIR_REL}"
ICON_PNG="${REPO_ROOT}/${ICON_PNG_REL}"

mkdir -p "${TOOLS_DIR}" "${OUT_DIR}"

echo "== cd repo root: ${REPO_ROOT} =="
cd "${REPO_ROOT}"

echo "== uv sync =="
uv sync

echo "== clean build/ dist/ =="
rm -rf build dist

SPEC_ROOT="${REPO_ROOT}/${APP_NAME}.spec"
echo "== remove root spec if present (Windows artifact) =="
if [[ -f "${SPEC_ROOT}" ]]; then
  echo "Removing ${SPEC_ROOT}"
  rm -f "${SPEC_ROOT}"
fi

echo "== pyinstaller -> dist/${APP_NAME} =="
# NOTE: Linux uses SRC:DEST for --add-data (colon)
uv run pyinstaller --noconfirm --name "${APP_NAME}" "${ENTRY}" \
  --add-data "backend:backend" \
  --add-data "frontend:frontend"

echo "== sanity check: dist binary exists =="
if [[ ! -x "dist/${APP_NAME}/${APP_NAME}" ]]; then
  echo "ERROR: Expected executable at dist/${APP_NAME}/${APP_NAME} but it was not found/executable."
  echo "Contents of dist/${APP_NAME}:"
  ls -la "dist/${APP_NAME}" || true
  exit 1
fi

echo "== sanity check: model file bundled =="
MODEL_REL="backend/models/hand_landmarker.task"
MODEL_A="dist/${APP_NAME}/_internal/${MODEL_REL}"
MODEL_B="dist/${APP_NAME}/${MODEL_REL}"

if [[ -f "${MODEL_A}" ]]; then
  echo "Found model at: ${MODEL_A}"
elif [[ -f "${MODEL_B}" ]]; then
  echo "Found model at: ${MODEL_B}"
else
  echo "ERROR: Missing ${MODEL_REL} inside dist/${APP_NAME}/ (checked both direct and _internal layouts)"
  echo "Tried:"
  echo "  ${MODEL_A}"
  echo "  ${MODEL_B}"
  echo "Searching dist for it:"
  find "dist/${APP_NAME}" -name "hand_landmarker.task" -print || true
  exit 1
fi

echo "== prepare AppDir =="
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin"

# Copy the entire PyInstaller folder output into AppDir/usr/bin/
cp -a "dist/${APP_NAME}/." "${APPDIR}/usr/bin/"

echo "== create AppRun =="
cat > "${APPDIR}/AppRun" <<EOF
#!/bin/sh
HERE="\$(dirname "\$(readlink -f "\$0")")"
exec "\$HERE/usr/bin/${APP_NAME}" "\$@"
EOF
chmod +x "${APPDIR}/AppRun"

echo "== create desktop file =="
cat > "${APPDIR}/${APP_NAME}.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=${APP_NAME}
Exec=${APP_NAME}
Icon=${APP_NAME}
Categories=Utility;
Terminal=false
EOF

echo "== add icon png =="
if [[ ! -f "${ICON_PNG}" ]]; then
  echo "ERROR: Missing icon: ${ICON_PNG}"
  echo "Create a PNG icon at ${ICON_PNG_REL}."
  exit 1
fi
cp "${ICON_PNG}" "${APPDIR}/${APP_NAME}.png"

echo "== ensure appimagetool exists =="
APPIMAGETOOL_PATH="${TOOLS_DIR}/${APPIMAGETOOL_NAME}"
if [[ ! -f "${APPIMAGETOOL_PATH}" ]]; then
  echo "Downloading appimagetool..."
  curl -L "${APPIMAGETOOL_URL}" -o "${APPIMAGETOOL_PATH}"
fi
chmod +x "${APPIMAGETOOL_PATH}"

echo "== ensure FUSE is installed for AppImage =="
if ! ldconfig -p 2>/dev/null | grep -q "libfuse.so.2"; then
  echo "Must instal libfuse2. Run:"
  echo "apt-get update"
  echo "apt-get install -y libfuse2"
  exit 1
else
  echo "libfuse2 already present."
fi

echo "== build AppImage =="
OUT_APPIMAGE="${OUT_DIR}/${APP_NAME}-x86_64.AppImage"
"${APPIMAGETOOL_PATH}" "${APPDIR}" "${OUT_APPIMAGE}"

if [[ "${CLEAN_BUILD_DIR}" -eq 1 ]]; then
  echo "== cleanup: removing PyInstaller build/ folder =="
  rm -rf build
fi

echo ""
echo "DONE."
echo "AppImage: ${OUT_APPIMAGE}"
chmod +x "${OUT_APPIMAGE}"
echo "Test by running ${OUT_APPIMAGE}"
