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


LOGICAL_TO_WINDOWS_VK: Dict[str, int] = {
    "escape": 0x1B,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
    "print_screen": 0x2C,
    "scroll_lock": 0x91,
    "pause": 0x13,
    "backtick": 0xC0,
    "1": 0x31,
    "2": 0x32,
    "3": 0x33,
    "4": 0x34,
    "5": 0x35,
    "6": 0x36,
    "7": 0x37,
    "8": 0x38,
    "9": 0x39,
    "0": 0x30,
    "minus": 0xBD,
    "equals": 0xBB,
    "backspace": 0x08,
    "insert": 0x2D,
    "home": 0x24,
    "page_up": 0x21,
    "tab": 0x09,
    "q": 0x51,
    "w": 0x57,
    "e": 0x45,
    "r": 0x52,
    "t": 0x54,
    "y": 0x59,
    "u": 0x55,
    "i": 0x49,
    "o": 0x4F,
    "p": 0x50,
    "left_bracket": 0xDB,
    "right_bracket": 0xDD,
    "backslash": 0xDC,
    "delete": 0x2E,
    "end": 0x23,
    "page_down": 0x22,
    "caps_lock": 0x14,
    "a": 0x41,
    "s": 0x53,
    "d": 0x44,
    "f": 0x46,
    "g": 0x47,
    "h": 0x48,
    "j": 0x4A,
    "k": 0x4B,
    "l": 0x4C,
    "semicolon": 0xBA,
    "quote": 0xDE,
    "enter": 0x0D,
    "left_shift": 0xA0,
    "right_shift": 0xA1,
    "z": 0x5A,
    "x": 0x58,
    "c": 0x43,
    "v": 0x56,
    "b": 0x42,
    "n": 0x4E,
    "m": 0x4D,
    "comma": 0xBC,
    "period": 0xBE,
    "slash": 0xBF,
    "arrow_up": 0x26,
    "left_ctrl": 0xA2,
    "left_win": 0x5B,
    "left_alt": 0xA4,
    "space": 0x20,
    "right_alt": 0xA5,
    "right_win": 0x5C,
    "menu": 0x5D,
    "right_ctrl": 0xA3,
    "arrow_left": 0x25,
    "arrow_down": 0x28,
    "arrow_right": 0x27,
    "num_lock": 0x90,
    "numpad_divide": 0x6F,
    "numpad_multiply": 0x6A,
    "numpad_subtract": 0x6D,
    "numpad_add": 0x6B,
    "numpad_enter": 0x0D,
    "numpad_decimal": 0x6E,
    "numpad0": 0x60,
    "numpad1": 0x61,
    "numpad2": 0x62,
    "numpad3": 0x63,
    "numpad4": 0x64,
    "numpad5": 0x65,
    "numpad6": 0x66,
    "numpad7": 0x67,
    "numpad8": 0x68,
    "numpad9": 0x69,
}


def get_windows_vk(key_code: str) -> Optional[int]:
    """Get Windows VK code for a logical key id."""
    key = normalize_key(key_code)
    return LOGICAL_TO_WINDOWS_VK.get(key)

