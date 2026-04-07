"""
Centralized key mappings getter for platform-agnostic access to key codes.

This module provides functions to get keyboard mappings for the current platform
without creating backend instances.
"""

import platform
from typing import Dict, Optional


def get_logical_to_key_mapping() -> Dict[str, any]:
    """
    Get the key mapping dictionary for the current platform.

    Returns:
        Dictionary mapping logical key names to platform-specific codes.
    """
    system = platform.system()

    if system == "Windows":
        from backend.platforms.WindowsKeyboardBackend import WindowsKeyboardBackend
        return WindowsKeyboardBackend.LOGICAL_TO_WINDOWS_VK
    elif system == "Linux":
        from backend.platforms.LinuxKeyboardBackend import LinuxKeyboardBackend
        return LinuxKeyboardBackend.LOGICAL_TO_XDOTOOL
    elif system == "Darwin":
        from backend.platforms.MacOSKeyboardBackend import MacOSKeyboardBackend
        return MacOSKeyboardBackend.LOGICAL_TO_MACOS

    # Fallback: return a basic cross-platform mapping
    return {
        "escape": "escape",
        "enter": "enter",
        "space": "space",
        "tab": "tab",
        "backspace": "backspace",
        "delete": "delete",
    }

