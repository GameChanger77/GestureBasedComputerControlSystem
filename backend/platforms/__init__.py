"""Platform-specific keyboard backends."""

from backend.platforms.PlatformKeyboardBackend import PlatformKeyboardBackend
from backend.platforms.KeyboardBackendFactory import create_keyboard_backend

__all__ = [
    "PlatformKeyboardBackend",
    "create_keyboard_backend",
]

