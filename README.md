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

Default source mode is `dev`.

Explicit modes:
```powershell
uv run python main.py --dev
uv run python main.py --prod
```

Bundled installer builds always run `prod` mode, even if `--dev` is passed.

## Verify environment
```powershell
uv run python --version
```
Expected output starts with `Python 3.11`.

## Camera permission
If prompted by your OS, allow camera access for Python/terminal.

## Branching and PR Workflow
1. Create a new branch for each issue or task you are working on.
2. Commit and push all related changes to that branch with clear, descriptive commit messages.
3. Open a pull request from your task branch into `dev` (not `main`).
4. Keep `main` for final deliverables/production. After work is merged into `dev` and validated, merge to `main` later.
