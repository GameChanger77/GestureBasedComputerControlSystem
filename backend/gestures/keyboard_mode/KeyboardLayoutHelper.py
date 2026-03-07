from __future__ import annotations

from typing import Dict, List, Tuple


class KeyboardLayoutHelper:
    MODIFIER_SLOT_TO_FAMILY = {
        "left_shift": "shift",
        "right_shift": "shift",
        "left_ctrl": "ctrl",
        "right_ctrl": "ctrl",
        "left_alt": "alt",
        "right_alt": "alt",
        "left_win": "win",
        "right_win": "win",
        "fn": "fn",
    }
    MODIFIER_FAMILY_TO_KEY = {
        "shift": "left_shift",
        "ctrl": "left_ctrl",
        "alt": "left_alt",
        "win": "left_win",
        "fn": None,
    }
    MODIFIER_FAMILY_TO_SLOTS = {
        "shift": ("left_shift", "right_shift"),
        "ctrl": ("left_ctrl", "right_ctrl"),
        "alt": ("left_alt", "right_alt"),
        "win": ("left_win", "right_win"),
        "fn": ("fn",),
    }
    MODIFIER_PRESS_ORDER: Tuple[str, ...] = ("win", "ctrl", "alt", "fn", "shift")

    FN_KEY_TO_FUNCTION = {
        "1": "f1",
        "2": "f2",
        "3": "f3",
        "4": "f4",
        "5": "f5",
        "6": "f6",
        "7": "f7",
        "8": "f8",
        "9": "f9",
        "0": "f10",
        "minus": "f11",
        "equals": "f12",
    }

    SHIFT_LABEL_BY_SLOT = {
        "backtick": "~",
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
        "minus": "_",
        "equals": "+",
        "left_bracket": "{",
        "right_bracket": "}",
        "backslash": "|",
        "semicolon": ":",
        "quote": "\"",
        "comma": "<",
        "period": ">",
        "slash": "?",
    }

    SUGGESTION_CHIP_COUNT = 3

    @staticmethod
    def _slot(slot_id: str, label: str, key: str, width: float = 1.0) -> Dict[str, object]:
        return {"id": slot_id, "label": label, "key": key, "w": width}

    @classmethod
    def build_unified_rows(cls, meta_key_label: str) -> List[List[Dict[str, object]]]:
        s = cls._slot
        return [
            [
                s("backtick", "`", "backtick"),
                s("1", "1", "1"),
                s("2", "2", "2"),
                s("3", "3", "3"),
                s("4", "4", "4"),
                s("5", "5", "5"),
                s("6", "6", "6"),
                s("7", "7", "7"),
                s("8", "8", "8"),
                s("9", "9", "9"),
                s("0", "0", "0"),
                s("minus", "-", "minus"),
                s("equals", "=", "equals"),
                s("backspace", "Back", "backspace", 1.8),
            ],
            [
                s("tab", "Tab", "tab", 1.4),
                s("q", "Q", "q"),
                s("w", "W", "w"),
                s("e", "E", "e"),
                s("r", "R", "r"),
                s("t", "T", "t"),
                s("y", "Y", "y"),
                s("u", "U", "u"),
                s("i", "I", "i"),
                s("o", "O", "o"),
                s("p", "P", "p"),
                s("left_bracket", "[", "left_bracket"),
                s("right_bracket", "]", "right_bracket"),
                s("backslash", "\\", "backslash"),
            ],
            [
                s("caps_lock", "Caps", "caps_lock", 1.7),
                s("a", "A", "a"),
                s("s", "S", "s"),
                s("d", "D", "d"),
                s("f", "F", "f"),
                s("g", "G", "g"),
                s("h", "H", "h"),
                s("j", "J", "j"),
                s("k", "K", "k"),
                s("l", "L", "l"),
                s("semicolon", ";", "semicolon"),
                s("quote", "'", "quote"),
                s("enter", "Enter", "enter", 1.8),
            ],
            [
                s("left_shift", "Shift", "left_shift", 2.0),
                s("z", "Z", "z"),
                s("x", "X", "x"),
                s("c", "C", "c"),
                s("v", "V", "v"),
                s("b", "B", "b"),
                s("n", "N", "n"),
                s("m", "M", "m"),
                s("comma", ",", "comma"),
                s("period", ".", "period"),
                s("slash", "/", "slash"),
                s("right_shift", "Shift", "right_shift", 1.8),
            ],
            [
                s("left_ctrl", "Ctrl", "left_ctrl", 1.2),
                s("left_win", meta_key_label, "left_win", 1.1),
                s("left_alt", "Alt", "left_alt", 1.1),
                s("fn", "Fn", "fn", 1.0),
                s("space", "Space", "space", 6.5),
                s("right_alt", "Alt", "right_alt", 1.1),
                s("right_win", meta_key_label, "right_win", 1.1),
                s("right_ctrl", "Ctrl", "right_ctrl", 1.2),
            ],
        ]

    @staticmethod
    def build_slot_key_map(rows: List[List[Dict[str, object]]]) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for row in rows:
            for slot in row:
                slot_id = str(slot["id"])
                mapping[slot_id] = str(slot["key"])
        return mapping
