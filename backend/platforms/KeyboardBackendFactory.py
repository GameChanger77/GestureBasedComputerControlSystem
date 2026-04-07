"""
Factory for creating platform-specific keyboard backends.

Handles platform detection and initialization of the appropriate keyboard backend.
"""

import platform
from typing import Optional

from backend.platforms.PlatformKeyboardBackend import PlatformKeyboardBackend


def get_keyboard_backend_class() -> type[PlatformKeyboardBackend]:
    """Get the keyboard backend class for the current platform."""
    system = platform.system()

    if system == "Windows":
        from backend.platforms.WindowsKeyboardBackend import WindowsKeyboardBackend

        return WindowsKeyboardBackend
    if system == "Darwin":
        from backend.platforms.MacOSKeyboardBackend import MacOSKeyboardBackend

        return MacOSKeyboardBackend
    if system == "Linux":
        from backend.platforms.LinuxKeyboardBackend import LinuxKeyboardBackend

        return LinuxKeyboardBackend

    raise RuntimeError(f"Unsupported operating system: {system}")


def create_keyboard_backend() -> PlatformKeyboardBackend:
    """
    Create and initialize the appropriate keyboard backend for the current platform.

    Returns:
        Initialized keyboard backend instance.

    Raises:
        RuntimeError: If backend cannot be initialized.
    """
    system = platform.system()
    backend_class = get_keyboard_backend_class()
    backend: Optional[PlatformKeyboardBackend] = backend_class()

    if not backend.initialize():
        reason = backend.get_failure_reason()
        raise RuntimeError(
            f"Failed to initialize {system} keyboard backend. "
            f"Reason: {reason or 'Unknown error'}"
        )

    return backend

