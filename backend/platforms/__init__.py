"""Platform-specific keyboard backends."""

from backend.platforms.PlatformKeyboardBackend import PlatformKeyboardBackend


def create_keyboard_backend():
    from backend.platforms.KeyboardBackendFactory import create_keyboard_backend as _create_keyboard_backend

    return _create_keyboard_backend()

__all__ = [
    "PlatformKeyboardBackend",
    "create_keyboard_backend",
]

