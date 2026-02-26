#!/usr/bin/env bash
set -euo pipefail

# ---------------- config ----------------
APP_NAME="gbccs"
ENTRY="main.py"
ICNS_REL="icons/gbccs_icon.icns"
OUT_DIR_REL="installers/mac/installer_out"

# Toggle: regenerate spec each run (like your earlier Windows script)
REGEN_SPEC=1   # set to 0 to keep existing spec

# Toggle: remove PyInstaller intermediate build/ folder at end
CLEAN_BUILD_DIR=1  # set to 0 to keep build/
# ---------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

ICNS_PATH="${REPO_ROOT}/${ICNS_REL}"
OUT_DIR="${REPO_ROOT}/${OUT_DIR_REL}"
SPEC_PATH="${REPO_ROOT}/${APP_NAME}.spec"

echo "== uv sync =="
uv sync

echo "== clean old outputs =="
rm -rf build dist
mkdir -p "${OUT_DIR}"

if [[ "${REGEN_SPEC}" -eq 1 ]]; then
  echo "== regenerate spec =="
  rm -f "${SPEC_PATH}"
fi

if [[ ! -f "${SPEC_PATH}" ]]; then
  echo "== spec not found -> generating =="
  # macOS uses SRC:DEST for add-data
  uv run pyinstaller \
    --noconfirm \
    --windowed \
    --name "${APP_NAME}" \
    --icon "${ICNS_PATH}" \
    --specpath "${REPO_ROOT}" \
    --add-data "backend:backend" \
    --add-data "frontend:frontend" \
    "${ENTRY}"
else
  echo "== using existing spec: ${SPEC_PATH} =="
fi

echo "== build using spec =="
uv run pyinstaller --noconfirm "${SPEC_PATH}"

echo "== sanity check .app exists =="
APP_PATH="dist/${APP_NAME}.app"
if [[ ! -d "${APP_PATH}" ]]; then
  echo "ERROR: expected ${APP_PATH} not found"
  exit 1
fi

APP_PLIST="${APP_PATH}/Contents/Info.plist"

echo "== add macOS privacy usage descriptions (Camera) =="
/usr/libexec/PlistBuddy -c "Add :NSCameraUsageDescription string \"GBCCS uses the camera to detect hand gestures for controlling your computer.\"" \
  "${APP_PLIST}" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Set :NSCameraUsageDescription \"GBCCS uses the camera to detect hand gestures for controlling your computer.\"" \
  "${APP_PLIST}"

echo "== build DMG (simple drag-to-Applications style) =="
DMG_PATH="${OUT_DIR}/${APP_NAME}.dmg"
TEMP_DMG="${OUT_DIR}/${APP_NAME}-temp.dmg"
STAGE_DIR="${OUT_DIR}/dmg_stage"

rm -f "${DMG_PATH}" "${TEMP_DMG}"
rm -rf "${STAGE_DIR}"
mkdir -p "${STAGE_DIR}"

# Copy app into staging
cp -R "${APP_PATH}" "${STAGE_DIR}/"

# Create an Applications shortcut (nice UX: drag app to Applications)
ln -s /Applications "${STAGE_DIR}/Applications"

# Create a writable temp DMG from the folder…
hdiutil create -volname "${APP_NAME}" -srcfolder "${STAGE_DIR}" -ov -format UDRW "${TEMP_DMG}" >/dev/null

# Convert to compressed read-only DMG
hdiutil convert "${TEMP_DMG}" -format UDZO -o "${DMG_PATH}" >/dev/null

# Cleanup staging/temp
rm -f "${TEMP_DMG}"
rm -rf "${STAGE_DIR}"

if [[ "${CLEAN_BUILD_DIR}" -eq 1 ]]; then
  echo "== cleanup: removing build/ =="
  rm -rf build
fi

echo ""
echo "DONE."
echo "App: ${REPO_ROOT}/dist/${APP_NAME}.app"
echo "DMG: ${DMG_PATH}"