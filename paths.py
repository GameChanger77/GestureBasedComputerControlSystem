import sys
from pathlib import Path

def app_root() -> Path:
    # If bundled by PyInstaller, files live under sys._MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    # If running from source, repo root
    return Path(__file__).resolve().parent

def resource(rel_path: str) -> Path:
    return app_root() / rel_path