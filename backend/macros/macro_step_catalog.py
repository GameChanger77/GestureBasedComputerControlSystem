from __future__ import annotations

from backend.platforms.KeyMappings import get_logical_to_key_mapping


def _build_key_options():
    seen = set()
    ordered_keys = [
        "left_ctrl",
        "right_ctrl",
        "left_alt",
        "right_alt",
        "left_shift",
        "right_shift",
        "left_win",
        "right_win",
        "delete",
        "enter",
        "escape",
        "tab",
        "space",
        "backspace",
        "arrow_left",
        "arrow_right",
        "arrow_up",
        "arrow_down",
    ]
    # Get platform-specific key mappings
    key_mapping = get_logical_to_key_mapping()
    ordered_keys.extend(sorted(key_mapping.keys()))
    options = []
    for key in ordered_keys:
        if key in seen:
            continue
        seen.add(key)
        options.append((key, key.replace("_", " ").title()))
    return options


KEY_OPTIONS = _build_key_options()


STEP_DEFINITIONS = {
    "tap_key": {
        "label": "Tap Key",
        "fields": [
            {"name": "key", "label": "Key", "type": "key", "default": "a"},
        ],
    },
    "key_down": {
        "label": "Key Down",
        "fields": [
            {"name": "key", "label": "Key", "type": "key", "default": "left_ctrl"},
        ],
    },
    "key_up": {
        "label": "Key Up",
        "fields": [
            {"name": "key", "label": "Key", "type": "key", "default": "left_ctrl"},
        ],
    },
    "tap_hotkey": {
        "label": "Tap Hotkey",
        "fields": [
            {"name": "keys", "label": "Keys", "type": "key_list", "default": ["left_ctrl", "left_alt", "delete"]},
        ],
    },
    "left_click": {
        "label": "Left Click",
        "fields": [],
    },
    "right_click": {
        "label": "Right Click",
        "fields": [],
    },
    "left_button_down": {
        "label": "Left Button Down",
        "fields": [],
    },
    "left_button_up": {
        "label": "Left Button Up",
        "fields": [],
    },
    "right_button_down": {
        "label": "Right Button Down",
        "fields": [],
    },
    "right_button_up": {
        "label": "Right Button Up",
        "fields": [],
    },
    "scroll": {
        "label": "Scroll",
        "fields": [
            {"name": "delta_x", "label": "Delta X", "type": "int", "default": 0, "min": -10000, "max": 10000},
            {"name": "delta_y", "label": "Delta Y", "type": "int", "default": -240, "min": -10000, "max": 10000},
        ],
    },
    "delay_ms": {
        "label": "Delay",
        "fields": [
            {"name": "duration_ms", "label": "Milliseconds", "type": "int", "default": 150, "min": 1, "max": 60000},
        ],
    },
}
