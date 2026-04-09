# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import os
import tomllib


SPEC_DIR = Path(
    os.environ.get("GBCCS_MAC_SPEC_DIR", str(Path.cwd() / "installers" / "mac"))
).resolve()
REPO_ROOT = Path(
    os.environ.get("GBCCS_REPO_ROOT", str(SPEC_DIR.parent.parent))
).resolve()
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

project_version = "0.1.0"
if PYPROJECT_PATH.exists():
    with PYPROJECT_PATH.open("rb") as fh:
        project_version = str(tomllib.load(fh).get("project", {}).get("version", project_version))

APP_NAME = "gbccs"
APP_ENTRY = str(REPO_ROOT / "main.py")
APP_ICON = str(REPO_ROOT / "icons" / "gbccs_icon.icns")
APP_VERSION = os.environ.get("APP_VERSION", project_version)
MACOS_BUNDLE_ID = os.environ.get("MACOS_BUNDLE_ID", "edu.iastate.gbccs")
TARGET_ARCH = os.environ.get("TARGET_ARCH") or None
CAMERA_USAGE = "GBCCS uses the camera to detect hand gestures for controlling your computer."

a = Analysis(
    [APP_ENTRY],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=[
        (str(REPO_ROOT / "backend"), "backend"),
        (str(REPO_ROOT / "frontend"), "frontend"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=TARGET_ARCH,
    codesign_identity=None,
    entitlements_file=None,
    icon=[APP_ICON],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=APP_ICON,
    bundle_identifier=MACOS_BUNDLE_ID,
    info_plist={
        "CFBundleIdentifier": MACOS_BUNDLE_ID,
        "CFBundleName": "GBCCS",
        "CFBundleDisplayName": "GBCCS",
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "NSCameraUsageDescription": CAMERA_USAGE,
        "NSHighResolutionCapable": True,
    },
)
