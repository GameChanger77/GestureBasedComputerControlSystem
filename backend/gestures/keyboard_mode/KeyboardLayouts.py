from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from backend.gestures.keyboard_mode.KeyCodes import normalize_key


@dataclass(frozen=True)
class KeyboardSlotDefinition:
    slot_id: str
    label: str
    key_code: str
    width: float = 1.0
    shift_label: str | None = None
    swipe_token: str | None = None

    def to_row_item(self) -> Dict[str, object]:
        return {
            "id": self.slot_id,
            "label": self.label,
            "key": self.key_code,
            "w": self.width,
            "shift_label": self.shift_label,
            "swipe_token": self.swipe_token,
        }


@dataclass(frozen=True)
class KeyboardLayoutDefinition:
    layout_id: str
    label: str
    rows: Tuple[Tuple[KeyboardSlotDefinition, ...], ...]

    def to_row_items(self) -> List[List[Dict[str, object]]]:
        return [[slot.to_row_item() for slot in row] for row in self.rows]


_SHIFTED_SYMBOLS = {
    "`": "~",
    "1": "!",
    "2": "@",
    "3": "#",
    "4": "$",
    "5": "%",
    "6": "^",
    "7": "&",
    "8": "*",
    "9": "(",
    "0": ")",
    "-": "_",
    "=": "+",
    "[": "{",
    "]": "}",
    "\\": "|",
    ";": ":",
    "'": "\"",
    ",": "<",
    ".": ">",
    "/": "?",
}

_PHYSICAL_ROWS: List[List[tuple[str, float]]] = [
    [
        ("backtick", 1.0), ("1", 1.0), ("2", 1.0), ("3", 1.0), ("4", 1.0), ("5", 1.0),
        ("6", 1.0), ("7", 1.0), ("8", 1.0), ("9", 1.0), ("0", 1.0), ("minus", 1.0),
        ("equals", 1.0), ("backspace", 1.8),
    ],
    [
        ("tab", 1.4), ("q", 1.0), ("w", 1.0), ("e", 1.0), ("r", 1.0), ("t", 1.0),
        ("y", 1.0), ("u", 1.0), ("i", 1.0), ("o", 1.0), ("p", 1.0), ("left_bracket", 1.0),
        ("right_bracket", 1.0), ("backslash", 1.0),
    ],
    [
        ("caps_lock", 1.7), ("a", 1.0), ("s", 1.0), ("d", 1.0), ("f", 1.0), ("g", 1.0),
        ("h", 1.0), ("j", 1.0), ("k", 1.0), ("l", 1.0), ("semicolon", 1.0), ("quote", 1.0),
        ("enter", 1.8),
    ],
    [
        ("left_shift", 2.0), ("z", 1.0), ("x", 1.0), ("c", 1.0), ("v", 1.0), ("b", 1.0),
        ("n", 1.0), ("m", 1.0), ("comma", 1.0), ("period", 1.0), ("slash", 1.0), ("right_shift", 1.8),
    ],
    [
        ("left_ctrl", 1.2), ("left_win", 1.1), ("left_alt", 1.1), ("fn", 1.0), ("space", 6.5),
        ("right_alt", 1.1), ("right_win", 1.1), ("right_ctrl", 1.2),
    ],
]

_SPECIAL_LABELS = {
    "backspace": "Back",
    "tab": "Tab",
    "caps_lock": "Caps",
    "enter": "Enter",
    "left_shift": "Shift",
    "right_shift": "Shift",
    "left_ctrl": "Ctrl",
    "right_ctrl": "Ctrl",
    "left_alt": "Alt",
    "right_alt": "Alt",
    "fn": "Fn",
    "space": "Space",
}

_QWERTY = {
    "backtick": "`", "1": "1", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7",
    "8": "8", "9": "9", "0": "0", "minus": "-", "equals": "=",
    "q": "q", "w": "w", "e": "e", "r": "r", "t": "t", "y": "y", "u": "u", "i": "i", "o": "o", "p": "p",
    "left_bracket": "[", "right_bracket": "]", "backslash": "\\",
    "a": "a", "s": "s", "d": "d", "f": "f", "g": "g", "h": "h", "j": "j", "k": "k", "l": "l",
    "semicolon": ";", "quote": "'",
    "z": "z", "x": "x", "c": "c", "v": "v", "b": "b", "n": "n", "m": "m", "comma": ",", "period": ".", "slash": "/",
}
_AZERTY = {
    **_QWERTY,
    "q": "a", "w": "z", "a": "q", "z": "w", "semicolon": "m", "m": ",", "comma": ";",
}
_QWERTZ = {**_QWERTY, "y": "z", "z": "y"}
_DVORAK = {
    **_QWERTY,
    "q": "'", "w": ",", "e": ".", "r": "p", "t": "y", "y": "f", "u": "g", "i": "c", "o": "r", "p": "l",
    "left_bracket": "/", "right_bracket": "=", "s": "o", "d": "e", "f": "u", "g": "i", "h": "d", "j": "h",
    "k": "t", "l": "n", "semicolon": "s", "quote": "-", "z": ";", "x": "q", "c": "j", "v": "k", "b": "x",
    "n": "b", "comma": "w", "period": "v", "slash": "z",
}
_COLEMAK = {
    **_QWERTY,
    "e": "f", "r": "p", "t": "g", "y": "j", "u": "l", "i": "u", "o": "y", "p": ";",
    "s": "r", "d": "s", "f": "t", "g": "d", "j": "n", "k": "e", "l": "i", "semicolon": "o", "n": "k",
}

_LAYOUTS = {
    "qwerty": ("QWERTY", _QWERTY),
    "azerty": ("AZERTY", _AZERTY),
    "qwertz": ("QWERTZ", _QWERTZ),
    "dvorak": ("Dvorak", _DVORAK),
    "colemak": ("Colemak", _COLEMAK),
}


def _label_for_value(slot_id: str, value: str, meta_key_label: str) -> str:
    if slot_id in ("left_win", "right_win"):
        return meta_key_label
    if slot_id in _SPECIAL_LABELS:
        return _SPECIAL_LABELS[slot_id]
    if len(value) == 1 and value.isalpha():
        return value.upper()
    return value


def _shift_label_for_value(value: str) -> str | None:
    if len(value) == 1 and value.isalpha():
        return value.upper()
    return _SHIFTED_SYMBOLS.get(value)


def _swipe_token_for_value(value: str) -> str | None:
    if len(value) == 1 and value.isalpha():
        return value.lower()
    return None


class KeyboardLayoutRegistry:
    @classmethod
    def list_options(cls) -> List[Dict[str, str]]:
        return [{"label": label, "value": layout_id} for layout_id, (label, _) in _LAYOUTS.items()]

    @classmethod
    def get(cls, layout_id: str, meta_key_label: str) -> KeyboardLayoutDefinition:
        normalized_layout = str(layout_id or "qwerty").strip().lower()
        label, mapping = _LAYOUTS.get(normalized_layout, _LAYOUTS["qwerty"])
        rows: List[Tuple[KeyboardSlotDefinition, ...]] = []
        for row in _PHYSICAL_ROWS:
            built_row = []
            for slot_id, width in row:
                output_value = mapping.get(slot_id, slot_id)
                built_row.append(
                    KeyboardSlotDefinition(
                        slot_id=slot_id,
                        label=_label_for_value(slot_id, output_value, meta_key_label),
                        key_code=normalize_key(output_value),
                        width=width,
                        shift_label=_shift_label_for_value(output_value),
                        swipe_token=_swipe_token_for_value(output_value),
                    )
                )
            rows.append(tuple(built_row))
        return KeyboardLayoutDefinition(
            layout_id=normalized_layout if normalized_layout in _LAYOUTS else "qwerty",
            label=label,
            rows=tuple(rows),
        )
