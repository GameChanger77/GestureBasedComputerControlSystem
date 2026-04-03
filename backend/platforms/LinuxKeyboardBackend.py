"""
Linux-specific keyboard input backend.

Supports both X11 (via xdotool) and Wayland (via ydotool) with automatic
fallback to pynput if neither is available.
"""

import os
import shutil
import subprocess
import time
from typing import List, Optional

from backend.platforms.PlatformKeyboardBackend import PlatformKeyboardBackend
from backend.gestures.keyboard_mode.KeyCodes import normalize_key
from pynput.keyboard import Controller as PyNputKeyboard, Key


class LinuxKeyboardBackend(PlatformKeyboardBackend):
    """Linux keyboard backend with X11/Wayland support."""

    def __init__(self):
        self._xdotool_path = shutil.which("xdotool")
        self._ydotool_path = shutil.which("ydotool")
        self._session_type = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()

        self._pynput_keyboard = None
        self._warned_missing_xdotool = False
        self._warned_missing_ydotool = False
        self._failure_reason = None
        self._held_keys = set()

    def initialize(self) -> bool:
        """Initialize Linux keyboard backend."""
        try:
            # Always have pynput as fallback
            self._pynput_keyboard = PyNputKeyboard()

            # Log what tools are available
            available_tools = []
            if self._xdotool_path:
                available_tools.append(f"xdotool ({self._xdotool_path})")
            if self._ydotool_path:
                available_tools.append(f"ydotool ({self._ydotool_path})")
            available_tools.append("pynput (fallback)")

            session_info = f"{self._session_type}" if self._session_type else "unknown"
            print(f"Linux keyboard backend initialized (session={session_info})")
            print(f"Available backends: {', '.join(available_tools)}")

            return True
        except Exception as e:
            self._failure_reason = f"Failed to initialize Linux keyboard backend: {e}"
            return False

    def shutdown(self):
        """Clean up resources."""
        self._release_all_keys()

    def is_available(self) -> bool:
        """Check if backend is available."""
        return self._pynput_keyboard is not None

    def _get_backend_order(self) -> List[str]:
        """
        Determine the order of backends to try based on session type.

        For Wayland, prefer ydotool over xdotool since xdotool doesn't work on Wayland.
        For X11, prefer xdotool as it's more mature.
        """
        preferred = []

        if self._session_type == "wayland":
            preferred = ["ydotool", "xdotool", "pynput"]
        else:
            preferred = ["xdotool", "ydotool", "pynput"]

        available = []
        for backend in preferred:
            if backend == "xdotool" and self._xdotool_path:
                available.append("xdotool")
            elif backend == "ydotool" and self._ydotool_path:
                available.append("ydotool")
            elif backend == "pynput":
                available.append("pynput")

        return available

    def _run_input_command(self, args: List[str]) -> bool:
        """Run an input command and return success status."""
        try:
            result = subprocess.run(
                args,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5.0,
            )
            return result.returncode == 0
        except Exception as e:
            print(f"Error running input command {args[0]}: {e}")
            return False

    def _logical_to_xdotool_key(self, logical: str) -> Optional[str]:
        """Convert logical key code to xdotool key name."""
        if len(logical) == 1:
            return logical

        key_lookup = {
            "backtick": "grave",
            "minus": "minus",
            "equals": "equal",
            "left_bracket": "bracketleft",
            "right_bracket": "bracketright",
            "backslash": "backslash",
            "semicolon": "semicolon",
            "quote": "apostrophe",
            "comma": "comma",
            "period": "period",
            "slash": "slash",
            "left_win": "Super_L",
            "right_win": "Super_R",
            "left_shift": "Shift_L",
            "right_shift": "Shift_R",
            "left_ctrl": "Control_L",
            "right_ctrl": "Control_R",
            "left_alt": "Alt_L",
            "right_alt": "Alt_R",
            "enter": "Return",
            "backspace": "BackSpace",
            "tab": "Tab",
            "escape": "Escape",
            "caps_lock": "Caps_Lock",
            "space": "space",
            "delete": "Delete",
            "insert": "Insert",
            "home": "Home",
            "end": "End",
            "page_up": "Page_Up",
            "page_down": "Page_Down",
            "arrow_left": "Left",
            "arrow_right": "Right",
            "arrow_up": "Up",
            "arrow_down": "Down",
            "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4", "f5": "F5",
            "f6": "F6", "f7": "F7", "f8": "F8", "f9": "F9", "f10": "F10",
            "f11": "F11", "f12": "F12",
            "print_screen": "Print",
            "scroll_lock": "Scroll_Lock",
            "pause": "Pause",
            "num_lock": "Num_Lock",
        }
        return key_lookup.get(logical)

    def _logical_to_ydotool_code(self, logical: str) -> Optional[int]:
        """Convert logical key code to ydotool key code."""
        if not logical:
            return None

        if len(logical) == 1:
            ch = logical.lower()
            alpha_codes = {
                "a": 30, "b": 48, "c": 46, "d": 32, "e": 18, "f": 33, "g": 34, "h": 35, "i": 23,
                "j": 36, "k": 37, "l": 38, "m": 50, "n": 49, "o": 24, "p": 25, "q": 16, "r": 19,
                "s": 31, "t": 20, "u": 22, "v": 47, "w": 17, "x": 45, "y": 21, "z": 44,
            }
            digit_codes = {"1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10, "0": 11}
            return alpha_codes.get(ch) or digit_codes.get(ch)

        key_lookup = {
            "backtick": 41,
            "minus": 12,
            "equals": 13,
            "left_bracket": 26,
            "right_bracket": 27,
            "backslash": 43,
            "semicolon": 39,
            "quote": 40,
            "comma": 51,
            "period": 52,
            "slash": 53,
            "tab": 15,
            "backspace": 14,
            "enter": 28,
            "space": 57,
            "escape": 1,
            "caps_lock": 58,
            "left_shift": 42,
            "right_shift": 54,
            "left_ctrl": 29,
            "right_ctrl": 97,
            "left_alt": 56,
            "right_alt": 100,
            "left_win": 125,
            "right_win": 126,
            "insert": 110,
            "delete": 111,
            "home": 102,
            "end": 107,
            "page_up": 104,
            "page_down": 109,
            "arrow_left": 105,
            "arrow_right": 106,
            "arrow_up": 103,
            "arrow_down": 108,
            "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63,
            "f6": 64, "f7": 65, "f8": 66, "f9": 67, "f10": 68,
            "f11": 87, "f12": 88,
            "print_screen": 99,
            "scroll_lock": 70,
            "pause": 119,
            "num_lock": 69,
        }
        return key_lookup.get(logical)

    def _tap_key_via_xdotool(self, logical: str) -> bool:
        """Tap a key using xdotool."""
        key = self._logical_to_xdotool_key(logical)
        if not key:
            return False
        return self._run_input_command([self._xdotool_path, "key", "--", key])

    def _tap_key_via_ydotool(self, logical: str) -> bool:
        """Tap a key using ydotool."""
        code = self._logical_to_ydotool_code(logical)
        if code is None:
            return False
        return self._run_input_command([self._ydotool_path, "key", f"{code}:1", f"{code}:0"])

    def _tap_key_via_pynput(self, logical: str) -> bool:
        """Tap a key using pynput."""
        try:
            key = self._pynput_key_from_logical(logical)
            if key is None:
                return False
            self._pynput_keyboard.press(key)
            time.sleep(0.005)
            self._pynput_keyboard.release(key)
            return True
        except Exception as e:
            print(f"Error tapping key via pynput: {e}")
            return False

    def _pynput_key_from_logical(self, logical: str) -> Optional:
        """Convert logical key to pynput Key object."""
        if len(logical) == 1:
            return logical

        key_lookup = {
            "tab": Key.tab,
            "backspace": Key.backspace,
            "enter": Key.enter,
            "space": Key.space,
            "escape": Key.esc,
            "caps_lock": Key.caps_lock,
            "left_shift": Key.shift_l,
            "right_shift": Key.shift_r,
            "left_ctrl": Key.ctrl_l,
            "right_ctrl": Key.ctrl_r,
            "left_alt": Key.alt_l,
            "right_alt": Key.alt_r,
            "left_win": Key.cmd,  # Fallback for super
            "right_win": Key.cmd,
            "insert": Key.insert,
            "delete": Key.delete,
            "home": Key.home,
            "end": Key.end,
            "page_up": Key.page_up,
            "page_down": Key.page_down,
            "arrow_left": Key.left,
            "arrow_right": Key.right,
            "arrow_up": Key.up,
            "arrow_down": Key.down,
            "f1": Key.f1, "f2": Key.f2, "f3": Key.f3, "f4": Key.f4, "f5": Key.f5,
            "f6": Key.f6, "f7": Key.f7, "f8": Key.f8, "f9": Key.f9, "f10": Key.f10,
            "f11": Key.f11, "f12": Key.f12,
        }
        return key_lookup.get(logical)

    def key_down(self, key_code: str) -> bool:
        """Press and hold a key."""
        logical = normalize_key(key_code)
        if not logical or logical in self._held_keys:
            return False

        try:
            key = self._pynput_key_from_logical(logical)
            if key is None:
                return False
            self._pynput_keyboard.press(key)
            self._held_keys.add(logical)
            return True
        except Exception as e:
            print(f"Error pressing key: {e}")
            return False

    def key_up(self, key_code: str) -> bool:
        """Release a held key."""
        logical = normalize_key(key_code)
        if not logical:
            return False

        try:
            key = self._pynput_key_from_logical(logical)
            if key is None:
                return False
            self._pynput_keyboard.release(key)
            self._held_keys.discard(logical)
            return True
        except Exception as e:
            print(f"Error releasing key: {e}")
            return False

    def tap_key(self, key_code: str) -> bool:
        """Press and release a key."""
        logical = normalize_key(key_code)
        if not logical:
            return False

        for backend in self._get_backend_order():
            if backend == "xdotool" and self._tap_key_via_xdotool(logical):
                return True
            elif backend == "ydotool" and self._tap_key_via_ydotool(logical):
                return True
            elif backend == "pynput" and self._tap_key_via_pynput(logical):
                return True

        return False

    def tap_hotkey(self, key_codes: List[str]) -> bool:
        """Press multiple keys together as a hotkey."""
        if not key_codes:
            return False

        logical_keys = [normalize_key(k) for k in key_codes]
        if not all(logical_keys):
            return False

        # Try xdotool first for X11
        if self._xdotool_path and self._session_type != "wayland":
            keys = []
            for logical in logical_keys:
                key = self._logical_to_xdotool_key(logical)
                if not key:
                    break
                keys.append(key)
            else:
                chord = "+".join(keys)
                if self._run_input_command([self._xdotool_path, "key", "--", chord]):
                    return True

        # Try ydotool for Wayland
        if self._ydotool_path and self._session_type == "wayland":
            codes = []
            for logical in logical_keys:
                code = self._logical_to_ydotool_code(logical)
                if code is None:
                    break
                codes.append(code)
            else:
                events = []
                for code in codes[:-1]:
                    events.append(f"{code}:1")
                events.append(f"{codes[-1]}:1")
                events.append(f"{codes[-1]}:0")
                for code in reversed(codes[:-1]):
                    events.append(f"{code}:0")
                if self._run_input_command([self._ydotool_path, "key", *events]):
                    return True

        # Fall back to pynput
        return self._tap_hotkey_via_pynput(logical_keys)

    def _tap_hotkey_via_pynput(self, logical_keys: List[str]) -> bool:
        """Tap a hotkey using pynput."""
        try:
            resolved_keys = []
            for logical in logical_keys:
                key = self._pynput_key_from_logical(logical)
                if key is None:
                    return False
                resolved_keys.append(key)

            for key in resolved_keys:
                self._pynput_keyboard.press(key)
            time.sleep(0.010)
            for key in reversed(resolved_keys):
                try:
                    self._pynput_keyboard.release(key)
                except Exception:
                    pass
            return True
        except Exception as e:
            print(f"Error tapping hotkey via pynput: {e}")
            return False

    def type_text(self, text: str) -> bool:
        """Type text."""
        if not text:
            return False

        # Try xdotool first for X11 (more reliable for text)
        if self._xdotool_path and self._session_type != "wayland":
            return self._run_input_command([self._xdotool_path, "type", "--clearmodifiers", "--delay", "0", "--", text])

        # Try ydotool for Wayland
        if self._ydotool_path and self._session_type == "wayland":
            return self._run_input_command([self._ydotool_path, "type", text])

        # Fall back to pynput
        try:
            self._pynput_keyboard.type(text)
            return True
        except Exception as e:
            print(f"Error typing text: {e}")
            return False

    def get_failure_reason(self) -> Optional[str]:
        """Get reason if backend is unavailable."""
        return self._failure_reason

    def _release_all_keys(self):
        """Release any currently held keys."""
        for logical in list(self._held_keys):
            try:
                key = self._pynput_key_from_logical(logical)
                if key is not None:
                    self._pynput_keyboard.release(key)
            except Exception as e:
                print(f"Error releasing key '{logical}': {e}")
        self._held_keys.clear()

