# Frontend Setup

## Prerequisites
- Complete the root setup in `../README.md`.
- Run commands from the repository root.

## Install dependencies
```powershell
uv sync
```

## Start the UI
```powershell
uv run python main.py
```

Default source mode is `dev`.

Explicit modes:
```powershell
uv run python main.py --dev
uv run python main.py --prod
```

Bundled installer builds always run `prod` mode, even if `--dev` is passed.

## Development loop
After frontend changes, restart the same run command to test updates.
