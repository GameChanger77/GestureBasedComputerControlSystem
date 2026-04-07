"""
Centralized platform keyboard metadata getters.

This module provides platform-specific keyboard mappings and labels without
creating backend instances.
"""

from typing import Dict

from backend.platforms.KeyboardBackendFactory import get_keyboard_backend_class


def get_logical_to_key_mapping() -> Dict[str, object]:
    """
    Get the key mapping dictionary for the current platform.

    Returns:
        Dictionary mapping logical key names to platform-specific codes.
    """
    backend_class = get_keyboard_backend_class()

    if hasattr(backend_class, "LOGICAL_TO_WINDOWS_VK"):
        return backend_class.LOGICAL_TO_WINDOWS_VK
    if hasattr(backend_class, "LOGICAL_TO_XDOTOOL"):
        return backend_class.LOGICAL_TO_XDOTOOL
    if hasattr(backend_class, "LOGICAL_TO_MACOS"):
        return backend_class.LOGICAL_TO_MACOS

    # Fallback: return a basic cross-platform mapping
    return {
        "escape": "escape",
        "enter": "enter",
        "space": "space",
        "tab": "tab",
        "backspace": "backspace",
        "delete": "delete",
    }


def get_meta_key_label() -> str:
    """Get the user-facing label for the current platform meta key."""
    return get_keyboard_backend_class().get_meta_key_label()

