# build_windows.ps1
$ErrorActionPreference = "Stop"

# ---- config ----
$APP_NAME = "gbccs"
$ENTRY    = "main.py"
$ICON     = "icons\gbccs_icon.ico"
$ISS_PATH = "installers\windows\windows_setup_wizard.iss"
$SPEC_PATH = "$APP_NAME.spec"
$CLEAN_BUILD_DIR = $true
# Bundled builds always enforce prod UI mode at runtime.
# --------------

$HERE = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO = Resolve-Path (Join-Path $HERE "..\..")

Write-Host "== cd to repo root: $REPO =="
Set-Location $REPO

Write-Host "== Sync deps (uv) =="
uv sync

Write-Host "== Clean old builds =="
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
Remove-Item -Force "$APP_NAME.spec" -ErrorAction SilentlyContinue

if (-not (Test-Path $SPEC_PATH)) {
  Write-Host "== Spec not found ($SPEC_PATH). Generating with PyInstaller =="
  # This generates the spec in repo root (specpath .)
  uv run pyinstaller `
    --noconfirm `
    --windowed `
    --name $APP_NAME `
    --icon $ICON `
    --specpath . `
    --add-data "backend;backend" `
    --add-data "frontend;frontend" `
    $ENTRY

  if (-not (Test-Path $SPEC_PATH)) {
    throw "Spec generation finished but $SPEC_PATH was not created. Check PyInstaller output above."
  }

  Write-Host "== Spec created: $SPEC_PATH =="
} else {
  Write-Host "== Using existing spec: $SPEC_PATH =="
}

Write-Host "== Build using spec =="
uv run pyinstaller "$APP_NAME.spec" --noconfirm

# ---- Inno Setup compile ----
# Try to find ISCC.exe automatically; fallback to common install path.
$ISCC = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $ISCC) {
  $fallback = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
  if (Test-Path $fallback) { $ISCC = $fallback }
}
if (-not $ISCC) {
  throw "Could not find ISCC.exe. Install Inno Setup or set `$ISCC to the full path."
}

Write-Host "== Compile Inno installer =="
& $ISCC $ISS_PATH

# ---- Optional cleanup ----
if ($CLEAN_BUILD_DIR) {
  Write-Host "== Removing PyInstaller build/ folder (safe) =="
  Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "DONE."
Write-Host "Built app: dist\$APP_NAME\"
Write-Host "Installer location: installers\windows\installer_out\"
