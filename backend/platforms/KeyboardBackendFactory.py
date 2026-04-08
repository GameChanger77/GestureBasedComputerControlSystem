"""
Factory for creating platform-specific keyboard backends.

Handles platform detection and initialization of the appropriate keyboard backend.
"""

import platform
from typing import Optional

from backend.platforms.PlatformKeyboardBackend import PlatformKeyboardBackend


def normalize_os_name(target_os: Optional[str] = None) -> str:
    """Normalize OS aliases to the canonical names used by the app."""
    if target_os is None:
        return platform.system()

    normalized = str(target_os).strip()
    lookup = {
        "windows": "Windows",
        "win": "Windows",
        "darwin": "Darwin",
        "mac": "Darwin",
        "macos": "Darwin",
        "osx": "Darwin",
        "linux": "Linux",
    }
    return lookup.get(normalized.lower(), normalized)


def get_keyboard_backend_class(target_os: Optional[str] = None) -> type[PlatformKeyboardBackend]:
    """Get the keyboard backend class for the requested platform."""
    system = normalize_os_name(target_os)

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


def create_keyboard_backend(target_os: Optional[str] = None) -> PlatformKeyboardBackend:
    """
    Create and initialize the appropriate keyboard backend for the current platform.

    Returns:
        Initialized keyboard backend instance.

    Raises:
        RuntimeError: If backend cannot be initialized.
    """
    system = normalize_os_name(target_os)
    backend_class = get_keyboard_backend_class(system)
    backend: Optional[PlatformKeyboardBackend] = backend_class()

    if not backend.initialize():
        reason = backend.get_failure_reason()
        raise RuntimeError(
            f"Failed to initialize {system} keyboard backend. "
            f"Reason: {reason or 'Unknown error'}"
        )

    return backend
