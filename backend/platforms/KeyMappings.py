"""
Centralized platform keyboard metadata getters.

This module provides platform-specific keyboard mappings and labels without
creating backend instances.
"""

from typing import Dict

from backend.platforms.KeyboardBackendFactory import get_keyboard_backend_class


def get_logical_to_key_mapping(target_os: str | None = None) -> Dict[str, object]:
    """
    Get the key mapping dictionary for the requested platform.

    Returns:
        Dictionary mapping logical key names to platform-specific codes.
    """
    backend_class = get_keyboard_backend_class(target_os)
    if getattr(backend_class, "KEY_MAPPING", None):
        return dict(backend_class.KEY_MAPPING)

    # Fallback: return a basic cross-platform mapping
    return {
        "escape": "escape",
        "enter": "enter",
        "space": "space",
        "tab": "tab",
        "backspace": "backspace",
        "delete": "delete",
    }


def get_meta_key_label(target_os: str | None = None) -> str:
    """Get the user-facing label for the requested platform meta key."""
    return get_keyboard_backend_class(target_os).get_meta_key_label()


def get_supported_logical_keys() -> list[str]:
    """Get a stable, host-independent superset of supported logical keys."""
    keys = set()
    for target_os in ("Windows", "Darwin", "Linux"):
        keys.update(get_logical_to_key_mapping(target_os).keys())

    keys.update({"left_cmd", "right_cmd"})
    return sorted(keys)
