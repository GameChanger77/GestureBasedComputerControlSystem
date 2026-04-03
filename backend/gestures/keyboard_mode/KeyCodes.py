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


# Extended key support for cross-platform compatibility
LOGICAL_TO_XDOTOOL = {
    "escape": "Escape",
    "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4", "f5": "F5",
    "f6": "F6", "f7": "F7", "f8": "F8", "f9": "F9", "f10": "F10",
    "f11": "F11", "f12": "F12",
    "print_screen": "Print",
    "scroll_lock": "Scroll_Lock",
    "pause": "Pause",
    "backtick": "grave",
    "minus": "minus",
    "equals": "equal",
    "backspace": "BackSpace",
    "tab": "Tab",
    "left_bracket": "bracketleft",
    "right_bracket": "bracketright",
    "backslash": "backslash",
    "caps_lock": "Caps_Lock",
    "semicolon": "semicolon",
    "quote": "apostrophe",
    "enter": "Return",
    "left_shift": "Shift_L",
    "right_shift": "Shift_R",
    "comma": "comma",
    "period": "period",
    "slash": "slash",
    "left_ctrl": "Control_L",
    "right_ctrl": "Control_R",
    "left_alt": "Alt_L",
    "right_alt": "Alt_R",
    "left_win": "Super_L",
    "right_win": "Super_R",
    "space": "space",
    "num_lock": "Num_Lock",
    "insert": "Insert",
    "delete": "Delete",
    "home": "Home",
    "end": "End",
    "page_up": "Page_Up",
    "page_down": "Page_Down",
    "arrow_up": "Up",
    "arrow_down": "Down",
    "arrow_left": "Left",
    "arrow_right": "Right",
    "numpad_divide": "KP_Divide",
    "numpad_multiply": "KP_Multiply",
    "numpad_subtract": "KP_Subtract",
    "numpad_add": "KP_Add",
    "numpad_enter": "KP_Enter",
    "numpad_decimal": "KP_Decimal",
    "numpad0": "KP_0", "numpad1": "KP_1", "numpad2": "KP_2", "numpad3": "KP_3",
    "numpad4": "KP_4", "numpad5": "KP_5", "numpad6": "KP_6", "numpad7": "KP_7",
    "numpad8": "KP_8", "numpad9": "KP_9",
}


def get_xdotool_key(key_code: str) -> Optional[str]:
    """Get xdotool key name for a logical key id."""
    key = normalize_key(key_code)
    if len(key) == 1:
        return key
    return LOGICAL_TO_XDOTOOL.get(key)

