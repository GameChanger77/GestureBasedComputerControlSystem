"""Platform-specific keyboard backends."""

from backend.platforms.PlatformKeyboardBackend import PlatformKeyboardBackend
from backend.platforms.KeyboardBackendFactory import (
    create_keyboard_backend,
    get_keyboard_backend_class,
    normalize_os_name,
)

__all__ = [
    "PlatformKeyboardBackend",
    "create_keyboard_backend",
    "get_keyboard_backend_class",
    "normalize_os_name",
]
