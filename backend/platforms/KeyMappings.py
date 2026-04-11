"""
Centralized platform keyboard metadata getters.

This module provides platform-specific keyboard mappings and labels without
creating backend instances.
"""

from typing import Dict, Iterable, List

from backend.gestures.keyboard_mode.KeyCodes import normalize_key
from backend.platforms.KeyboardBackendFactory import get_keyboard_backend_class
from backend.platforms.KeyboardBackendFactory import normalize_os_name


_SHORTCUT_PRIORITY_KEYS = [
    "left_ctrl",
    "right_ctrl",
    "left_alt",
    "right_alt",
    "left_shift",
    "right_shift",
    "left_cmd",
    "right_cmd",
    "left_win",
    "right_win",
    "delete",
    "backspace",
    "enter",
    "escape",
    "tab",
    "space",
    "arrow_left",
    "arrow_right",
    "arrow_up",
    "arrow_down",
]

_DYNAMIC_CHARACTER_KEYS = list("abcdefghijklmnopqrstuvwxyz0123456789")

_SHORTCUT_LABELS = {
    "left_ctrl": "Ctrl",
    "right_ctrl": "Right Ctrl",
    "left_alt": "Alt",
    "right_alt": "Right Alt",
    "left_shift": "Shift",
    "right_shift": "Right Shift",
    "left_cmd": "Cmd",
    "right_cmd": "Right Cmd",
    "left_win": "Win",
    "right_win": "Right Win",
    "escape": "Esc",
    "backspace": "Backspace",
    "delete": "Delete",
    "space": "Space",
    "tab": "Tab",
    "enter": "Enter",
    "arrow_left": "Left Arrow",
    "arrow_right": "Right Arrow",
    "arrow_up": "Up Arrow",
    "arrow_down": "Down Arrow",
    "page_up": "Page Up",
    "page_down": "Page Down",
    "caps_lock": "Caps Lock",
    "scroll_lock": "Scroll Lock",
    "num_lock": "Num Lock",
    "print_screen": "Print Screen",
    "left_bracket": "[",
    "right_bracket": "]",
    "backslash": "\\",
    "semicolon": ";",
    "quote": "'",
    "comma": ",",
    "period": ".",
    "slash": "/",
    "minus": "-",
    "equals": "=",
    "backtick": "`",
}


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


def get_supported_logical_keys(target_os: str | None = None) -> list[str]:
    """Get supported logical keys for one OS, or a stable cross-platform superset."""
    if target_os is not None:
        keys = set(get_logical_to_key_mapping(target_os).keys())
        keys.update(_DYNAMIC_CHARACTER_KEYS)
        return sorted(keys)

    keys = set()
    for candidate_os in ("Windows", "Darwin", "Linux"):
        keys.update(get_logical_to_key_mapping(candidate_os).keys())
    keys.update(_DYNAMIC_CHARACTER_KEYS)
    keys.update({"left_cmd", "right_cmd"})
    return sorted(keys)


def get_supported_shortcut_keys(target_os: str | None = None) -> list[str]:
    """Return the allowed shortcut keys for the requested OS."""
    system = normalize_os_name(target_os)
    keys = set(get_logical_to_key_mapping(system).keys())
    keys.update(_DYNAMIC_CHARACTER_KEYS)

    if system == "Darwin":
        keys.discard("left_win")
        keys.discard("right_win")
        keys.update({"left_cmd", "right_cmd"})
    else:
        keys.discard("left_cmd")
        keys.discard("right_cmd")

    ordered: List[str] = []
    seen = set()
    for key in _SHORTCUT_PRIORITY_KEYS:
        if key in keys and key not in seen:
            ordered.append(key)
            seen.add(key)
    for key in sorted(keys):
        if key not in seen:
            ordered.append(key)
            seen.add(key)
    return ordered


def format_shortcut_key_label(logical_key: str, target_os: str | None = None) -> str:
    """Format a logical shortcut key for user-facing UI."""
    system = normalize_os_name(target_os)
    logical = str(logical_key).strip()
    if not logical:
        return ""

    if system == "Darwin":
        if logical == "left_alt":
            return "Option"
        if logical == "right_alt":
            return "Right Option"
        if logical == "left_cmd":
            return "Cmd"
        if logical == "right_cmd":
            return "Right Cmd"
    else:
        meta_label = get_meta_key_label(system)
        if logical == "left_win":
            return meta_label
        if logical == "right_win":
            return f"Right {meta_label}"

    label = _SHORTCUT_LABELS.get(logical)
    if label is not None:
        return label
    if len(logical) == 1:
        return logical.upper()
    return logical.replace("_", " ").title()


def get_shortcut_key_options(target_os: str | None = None) -> list[tuple[str, str]]:
    """Return ordered key options for shortcut editors."""
    system = normalize_os_name(target_os)
    return [
        (key, format_shortcut_key_label(key, system))
        for key in get_supported_shortcut_keys(system)
    ]


def normalize_shortcut_key(key_code: str, target_os: str | None = None) -> str:
    """Normalize a user-entered shortcut key to an allowed logical key for one OS."""
    system = normalize_os_name(target_os)
    if key_code is None:
        return ""

    raw = str(key_code).strip().lower()
    if not raw:
        return ""

    meta_key = "left_cmd" if system == "Darwin" else "left_win"
    alias_map = {
        "ctrl": "left_ctrl",
        "control": "left_ctrl",
        "shift": "left_shift",
        "alt": "left_alt",
        "option": "left_alt",
        "cmd": meta_key,
        "command": meta_key,
        "meta": meta_key,
        "super": meta_key,
        "win": meta_key,
        "windows": meta_key,
        "cmd_l": "left_cmd",
        "cmd_r": "right_cmd",
        "super_l": "left_win",
        "super_r": "right_win",
    }

    normalized = normalize_key(alias_map.get(raw, raw))
    if system == "Darwin":
        if normalized == "left_win":
            normalized = "left_cmd"
        elif normalized == "right_win":
            normalized = "right_cmd"
    else:
        if normalized == "left_cmd":
            normalized = "left_win"
        elif normalized == "right_cmd":
            normalized = "right_win"

    return normalized if normalized in set(get_supported_shortcut_keys(system)) else ""


def normalize_shortcut_keys(
    key_codes: Iterable[str] | str,
    target_os: str | None = None,
) -> list[str]:
    """Normalize and validate a shortcut chord for the requested OS."""
    system = normalize_os_name(target_os)
    if isinstance(key_codes, str):
        raw_items = [item.strip() for item in key_codes.split(",")]
    elif isinstance(key_codes, Iterable):
        raw_items = [str(item).strip() for item in key_codes]
    else:
        raise ValueError("shortcut keys must be a list of keys")

    normalized_keys: list[str] = []
    seen = set()
    for item in raw_items:
        if not item:
            continue
        normalized = normalize_shortcut_key(item, system)
        if not normalized:
            raise ValueError(f"'{item}' is not a valid {system} shortcut key")
        if normalized not in seen:
            normalized_keys.append(normalized)
            seen.add(normalized)

    if not normalized_keys:
        raise ValueError("shortcut_keys must contain at least one valid key")
    return normalized_keys


def summarize_shortcut_keys(key_codes: Iterable[str], target_os: str | None = None) -> str:
    """Build a user-facing summary such as 'Ctrl + Shift + S'."""
    system = normalize_os_name(target_os)
    return " + ".join(format_shortcut_key_label(key, system) for key in key_codes)
