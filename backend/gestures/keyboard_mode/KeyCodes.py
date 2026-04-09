"""
Logical key identifiers and OS-specific mappings.

The gesture pipeline should only use logical key ids. Action backends map these
ids to platform key codes.
"""

from typing import Dict, Optional


def normalize_key(key_code: str) -> str:
    """Normalize user/logical key names to canonical ids."""
    if key_code is None:
        return ""

    key = str(key_code).strip().lower()
    aliases = {
        "`": "backtick",
        "~": "backtick",
        "-": "minus",
        "_": "minus",
        "=": "equals",
        "+": "equals",
        "[": "left_bracket",
        "]": "right_bracket",
        "\\": "backslash",
        ";": "semicolon",
        ":": "semicolon",
        "'": "quote",
        "\"": "quote",
        ",": "comma",
        "<": "comma",
        ".": "period",
        ">": "period",
        "/": "slash",
        "?": "slash",
        "ctrl": "left_ctrl",
        "control": "left_ctrl",
        "shift": "left_shift",
        "alt": "left_alt",
        "win": "left_win",
        "cmd": "left_win",
        "return": "enter",
        "del": "delete",
        "esc": "escape",
    }
    return aliases.get(key, key)


MODIFIER_KEYS = {
    "left_shift",
    "right_shift",
    "left_ctrl",
    "right_ctrl",
    "left_alt",
    "right_alt",
    "left_win",
    "right_win",
}

LOCK_KEYS = {"caps_lock", "num_lock", "scroll_lock"}

REPEATABLE_KEYS = {
    "backspace",
    "delete",
    "space",
    "arrow_left",
    "arrow_right",
    "arrow_up",
    "arrow_down",
}


