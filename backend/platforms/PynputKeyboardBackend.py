"""
Shared pynput-based keyboard backend.

Used as the degraded keyboard transport for injected test controllers,
cross-host OS simulation, and native backend initialization fallback.
"""

import time
from typing import List, Optional

from backend.gestures.keyboard_mode.KeyCodes import normalize_key
from backend.platforms.PlatformKeyboardBackend import PlatformKeyboardBackend

try:
    from pynput.keyboard import Key
except ImportError:
    class Key:
        tab = "tab"
        backspace = "backspace"
        enter = "enter"
        space = "space"
        esc = "esc"
        caps_lock = "caps_lock"
        shift_l = "shift_l"
        shift_r = "shift_r"
        ctrl_l = "ctrl_l"
        ctrl_r = "ctrl_r"
        alt_l = "alt_l"
        alt_r = "alt_r"
        cmd = "cmd"
        cmd_l = "cmd_l"
        cmd_r = "cmd_r"
        super_l = "super_l"
        super_r = "super_r"
        insert = "insert"
        delete = "delete"
        home = "home"
        end = "end"
        page_up = "page_up"
        page_down = "page_down"
        left = "left"
        right = "right"
        up = "up"
        down = "down"
        f1 = "f1"
        f2 = "f2"
        f3 = "f3"
        f4 = "f4"
        f5 = "f5"
        f6 = "f6"
        f7 = "f7"
        f8 = "f8"
        f9 = "f9"
        f10 = "f10"
        f11 = "f11"
        f12 = "f12"


class PynputKeyboardBackend(PlatformKeyboardBackend):
    """Lightweight keyboard backend used when native platform backends are unavailable."""

    KEY_MAPPING = {}

    def __init__(self, keyboard_controller, os_type: str):
        self._keyboard = keyboard_controller
        self._os_type = str(os_type)
        self._held_keys = set()

    def initialize(self) -> bool:
        return True

    def shutdown(self):
        self.release_all_keys()

    def is_available(self) -> bool:
        return self._keyboard is not None

    def get_failure_reason(self) -> Optional[str]:
        return None

    def _pynput_meta_key(self, side: str):
        is_left = side == "left"
        side_super = "super_l" if is_left else "super_r"
        side_cmd = "cmd_l" if is_left else "cmd_r"

        if self._os_type == "Linux":
            return (
                getattr(Key, side_super, None)
                or getattr(Key, side_cmd, None)
                or getattr(Key, "cmd", None)
            )
        if self._os_type == "Darwin":
            return getattr(Key, side_cmd, None) or getattr(Key, "cmd", None)
        return getattr(Key, side_cmd, None) or getattr(Key, "cmd", None)

    def _resolve_key(self, key_code: str):
        logical = normalize_key(key_code)
        if not logical:
            return None

        if len(logical) == 1:
            return logical

        punct = {
            "backtick": "`",
            "minus": "-",
            "equals": "=",
            "left_bracket": "[",
            "right_bracket": "]",
            "backslash": "\\",
            "semicolon": ";",
            "quote": "'",
            "comma": ",",
            "period": ".",
            "slash": "/",
        }
        if logical in punct:
            return punct[logical]

        key_lookup = {
            "tab": getattr(Key, "tab", None),
            "backspace": getattr(Key, "backspace", None),
            "enter": getattr(Key, "enter", None),
            "space": getattr(Key, "space", None),
            "escape": getattr(Key, "esc", None),
            "caps_lock": getattr(Key, "caps_lock", None),
            "left_shift": getattr(Key, "shift_l", None),
            "right_shift": getattr(Key, "shift_r", None),
            "left_ctrl": getattr(Key, "ctrl_l", None),
            "right_ctrl": getattr(Key, "ctrl_r", None),
            "left_alt": getattr(Key, "alt_l", None),
            "right_alt": getattr(Key, "alt_r", None),
            "left_win": self._pynput_meta_key("left"),
            "right_win": self._pynput_meta_key("right"),
            "left_cmd": self._pynput_meta_key("left"),
            "right_cmd": self._pynput_meta_key("right"),
            "insert": getattr(Key, "insert", None),
            "delete": getattr(Key, "delete", None),
            "home": getattr(Key, "home", None),
            "end": getattr(Key, "end", None),
            "page_up": getattr(Key, "page_up", None),
            "page_down": getattr(Key, "page_down", None),
            "arrow_left": getattr(Key, "left", None),
            "arrow_right": getattr(Key, "right", None),
            "arrow_up": getattr(Key, "up", None),
            "arrow_down": getattr(Key, "down", None),
            "f1": getattr(Key, "f1", None),
            "f2": getattr(Key, "f2", None),
            "f3": getattr(Key, "f3", None),
            "f4": getattr(Key, "f4", None),
            "f5": getattr(Key, "f5", None),
            "f6": getattr(Key, "f6", None),
            "f7": getattr(Key, "f7", None),
            "f8": getattr(Key, "f8", None),
            "f9": getattr(Key, "f9", None),
            "f10": getattr(Key, "f10", None),
            "f11": getattr(Key, "f11", None),
            "f12": getattr(Key, "f12", None),
        }
        return key_lookup.get(logical)

    def key_down(self, key_code: str) -> bool:
        logical = normalize_key(key_code)
        if not logical or logical in self._held_keys:
            return False

        key = self._resolve_key(logical)
        if key is None:
            return False

        try:
            self._keyboard.press(key)
            self._held_keys.add(logical)
            return True
        except Exception:
            return False

    def key_up(self, key_code: str) -> bool:
        logical = normalize_key(key_code)
        if not logical:
            return False

        key = self._resolve_key(logical)
        if key is None:
            return False

        try:
            self._keyboard.release(key)
            self._held_keys.discard(logical)
            return True
        except Exception:
            return False

    def tap_key(self, key_code: str) -> bool:
        logical = normalize_key(key_code)
        if not logical:
            return False

        key = self._resolve_key(logical)
        if key is None:
            return False

        try:
            self._keyboard.press(key)
            time.sleep(0.005)
            self._keyboard.release(key)
            return True
        except Exception:
            return False

    def tap_hotkey(self, key_codes: List[str]) -> bool:
        if not key_codes:
            return False

        resolved_keys = []
        for key_code in key_codes:
            key = self._resolve_key(key_code)
            if key is None:
                return False
            resolved_keys.append(key)

        try:
            for key in resolved_keys:
                self._keyboard.press(key)
            time.sleep(0.010)
        except Exception:
            return False
        finally:
            for key in reversed(resolved_keys):
                try:
                    self._keyboard.release(key)
                except Exception:
                    pass

        return True

    def type_text(self, text: str) -> bool:
        if not text:
            return False

        try:
            self._keyboard.type(text)
            return True
        except Exception:
            return False

    def release_all_keys(self):
        for logical in list(self._held_keys):
            self.key_up(logical)
        self._held_keys.clear()
