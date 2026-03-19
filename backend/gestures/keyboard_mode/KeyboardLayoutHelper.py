from __future__ import annotations

from typing import Dict, List, Tuple

from backend.gestures.keyboard_mode.KeyboardLayouts import KeyboardLayoutRegistry


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

    SUGGESTION_CHIP_COUNT = 3

    @classmethod
    def build_unified_rows(cls, meta_key_label: str, layout_id: str = "qwerty") -> List[List[Dict[str, object]]]:
        layout = KeyboardLayoutRegistry.get(layout_id, meta_key_label)
        return layout.to_row_items()

    @staticmethod
    def build_slot_key_map(rows: List[List[Dict[str, object]]]) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for row in rows:
            for slot in row:
                slot_id = str(slot["id"])
                mapping[slot_id] = str(slot["key"])
        return mapping

    @staticmethod
    def build_slot_shift_label_map(rows: List[List[Dict[str, object]]]) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for row in rows:
            for slot in row:
                shift_label = slot.get("shift_label")
                if shift_label:
                    mapping[str(slot["id"])] = str(shift_label)
        return mapping

    @staticmethod
    def build_slot_swipe_token_map(rows: List[List[Dict[str, object]]]) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for row in rows:
            for slot in row:
                swipe_token = slot.get("swipe_token")
                if swipe_token:
                    mapping[str(slot["id"])] = str(swipe_token)
        return mapping
