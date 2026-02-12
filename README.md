# Setup

## Prerequisites
- Python 3.11
- `uv`

## Install `uv` (Windows)
```powershell
winget install --id=astral-sh.uv -e
```

## Install dependencies
Run this from the repository root:
```powershell
uv sync
```

## Run the application
Run this from the repository root:
```powershell
uv run python main.py
```

## Verify environment
```powershell
uv run python --version
```
Expected output starts with `Python 3.11`.

## Camera permission
If prompted by your OS, allow camera access for Python/terminal.
