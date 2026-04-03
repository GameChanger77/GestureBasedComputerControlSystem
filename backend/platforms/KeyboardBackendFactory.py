"""
Factory for creating platform-specific keyboard backends.

Handles platform detection and initialization of the appropriate keyboard backend.
"""

import platform
from typing import Optional

from backend.platforms.PlatformKeyboardBackend import PlatformKeyboardBackend
from backend.platforms.WindowsKeyboardBackend import WindowsKeyboardBackend
from backend.platforms.LinuxKeyboardBackend import LinuxKeyboardBackend
from backend.platforms.MacOSKeyboardBackend import MacOSKeyboardBackend


def create_keyboard_backend() -> PlatformKeyboardBackend:
    """
    Create and initialize the appropriate keyboard backend for the current platform.

    Returns:
        Initialized keyboard backend instance.

    Raises:
        RuntimeError: If backend cannot be initialized.
    """
    system = platform.system()
    backend: Optional[PlatformKeyboardBackend] = None

    if system == "Windows":
        backend = WindowsKeyboardBackend()
    elif system == "Darwin":
        backend = MacOSKeyboardBackend()
    elif system == "Linux":
        backend = LinuxKeyboardBackend()
    else:
        raise RuntimeError(f"Unsupported operating system: {system}")

    if not backend.initialize():
        reason = backend.get_failure_reason()
        raise RuntimeError(
            f"Failed to initialize {system} keyboard backend. "
            f"Reason: {reason or 'Unknown error'}"
        )

    return backend

