"""
Windows-specific keyboard input backend using SendInput.

Uses native Windows API for reliable keyboard injection without requiring
system accessibility permissions.
"""

import ctypes
from ctypes import wintypes
from typing import Dict, List, Optional

from backend.platforms.PlatformKeyboardBackend import PlatformKeyboardBackend
from backend.gestures.keyboard_mode.KeyCodes import normalize_key


class WindowsKeyboardBackend(PlatformKeyboardBackend):
    """Windows keyboard backend using SendInput API."""

    META_KEY_LABEL = "Win"

    # Windows Virtual Key codes mapping
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

    def __init__(self):
        self.INPUT_KEYBOARD = 1
        self.KEYEVENTF_KEYUP = 0x0002
        self._MAX_CONSECUTIVE_SEND_FAILS = 10

        self._send_input = None
        self._get_last_error = None
        self._INPUTUNION = None
        self._KEYBDINPUT = None
        self._INPUT = None

        self._keyboard_send_failures = 0
        self._keyboard_disabled = False
        self._failure_reason = None

        self._held_keys = set()

    @staticmethod
    def get_windows_vk_static(key_code: str) -> Optional[int]:
        """Static method to get Windows VK code for a logical key id."""
        key = normalize_key(key_code)
        return WindowsKeyboardBackend.LOGICAL_TO_WINDOWS_VK.get(key)

    def initialize(self) -> bool:
        """Initialize Windows keyboard structures."""
        try:
            ULONG_PTR = wintypes.WPARAM

            class MOUSEINPUT(ctypes.Structure):
                _fields_ = [
                    ("dx", wintypes.LONG),
                    ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR),
                ]

            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [
                    ("wVk", wintypes.WORD),
                    ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR),
                ]

            class HARDWAREINPUT(ctypes.Structure):
                _fields_ = [
                    ("uMsg", wintypes.DWORD),
                    ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD),
                ]

            class _INPUTUNION(ctypes.Union):
                _fields_ = [
                    ("mi", MOUSEINPUT),
                    ("ki", KEYBDINPUT),
                    ("hi", HARDWAREINPUT),
                ]

            class INPUT(ctypes.Structure):
                _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]

            self._send_input = ctypes.windll.user32.SendInput
            # Note: Don't use ctypes.POINTER() in argtypes - let ctypes handle pointer conversion
            # Use None for pointer arguments to disable type checking
            self._send_input.argtypes = None  # Disable argtypes checking
            self._send_input.restype = wintypes.UINT

            self._get_last_error = ctypes.windll.kernel32.GetLastError
            self._get_last_error.argtypes = ()
            self._get_last_error.restype = wintypes.DWORD

            self._INPUTUNION = _INPUTUNION
            self._KEYBDINPUT = KEYBDINPUT
            self._INPUT = INPUT
            self._INPUT_ARRAY = INPUT * 1  # Pre-create array type

            return True
        except Exception as e:
            self._failure_reason = f"Failed to initialize Windows keyboard backend: {e}"
            return False

    def shutdown(self):
        """Clean up resources."""
        self._release_all_keys()

    def get_windows_vk(self, key_code: str) -> Optional[int]:
        """Get Windows VK code for a logical key id."""
        key = normalize_key(key_code)
        return self.LOGICAL_TO_WINDOWS_VK.get(key)

    def is_available(self) -> bool:
        """Check if backend is available."""
        return not self._keyboard_disabled and self._send_input is not None

    def _send_key_event(self, vk_code: int, key_up: bool = False) -> bool:
        """
        Send a key event using Windows SendInput.

        Args:
            vk_code: Virtual key code
            key_up: If True, sends key release; if False, sends key press

        Returns:
            True if successful, False otherwise.
        """
        if self._keyboard_disabled:
            return False

        flags = self.KEYEVENTF_KEYUP if key_up else 0
        input_obj = self._INPUT(
            type=self.INPUT_KEYBOARD,
            union=self._INPUTUNION(
                ki=self._KEYBDINPUT(
                    wVk=vk_code,
                    wScan=0,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )

        # Create array and pass to SendInput
        input_array = self._INPUT_ARRAY(input_obj)
        sent = self._send_input(1, input_array, ctypes.sizeof(self._INPUT))
        if sent != 1:
            self._keyboard_send_failures += 1
            if self._keyboard_send_failures == 1:
                err = self._get_last_error()
                print(f"Keyboard SendInput failed (vk={vk_code}, key_up={key_up}, winerr={err})")
            if self._keyboard_send_failures >= self._MAX_CONSECUTIVE_SEND_FAILS:
                self._keyboard_disabled = True
                print("Keyboard input disabled after repeated SendInput failures")
                self._failure_reason = "Too many SendInput failures"
            return False

        self._keyboard_send_failures = 0
        return True

    def key_down(self, key_code: str) -> bool:
        """Press and hold a key."""
        logical = normalize_key(key_code)
        if not logical:
            return False

        if logical in self._held_keys:
            return False

        vk_code = self.get_windows_vk(logical)
        if vk_code is None:
            return False

        if self._send_key_event(vk_code, key_up=False):
            self._held_keys.add(logical)
            return True
        return False

    def key_up(self, key_code: str) -> bool:
        """Release a held key."""
        logical = normalize_key(key_code)
        if not logical:
            return False

        vk_code = self.get_windows_vk(logical)
        if vk_code is None:
            return False

        result = self._send_key_event(vk_code, key_up=True)
        self._held_keys.discard(logical)
        return result

    def tap_key(self, key_code: str) -> bool:
        """Press and release a key."""
        logical = normalize_key(key_code)
        if not logical:
            return False

        vk_code = self.get_windows_vk(logical)
        if vk_code is None:
            return False

        return self._send_key_event(vk_code, key_up=False) and self._send_key_event(vk_code, key_up=True)

    def tap_hotkey(self, key_codes: List[str]) -> bool:
        """Press multiple keys together as a hotkey."""
        if not key_codes:
            return False

        logical_keys = []
        vk_codes = []

        for key_code in key_codes:
            logical = normalize_key(key_code)
            if not logical:
                return False
            vk_code = self.get_windows_vk(logical)
            if vk_code is None:
                return False
            logical_keys.append(logical)
            vk_codes.append(vk_code)

        # Press all keys
        for vk_code in vk_codes:
            if not self._send_key_event(vk_code, key_up=False):
                # Release already-pressed keys on failure
                for pressed_vk in vk_codes[:vk_codes.index(vk_code)]:
                    self._send_key_event(pressed_vk, key_up=True)
                return False

        # Release all keys in reverse order
        success = True
        for vk_code in reversed(vk_codes):
            if not self._send_key_event(vk_code, key_up=True):
                success = False

        # Clear held keys tracking for this hotkey
        for logical in logical_keys:
            self._held_keys.discard(logical)

        return success

    def type_text(self, text: str) -> bool:
        """
        Type text using Unicode SendInput for direct character injection.

        This approach sends unicode characters directly without clipboard interference,
        making it faster and more reliable than clipboard-based methods.
        """
        if not text:
            return False

        try:
            # Send each character as unicode
            for char in text:
                # Get unicode value
                unicode_val = ord(char)

                # Create unicode key event (down)
                input_obj_down = self._INPUT(
                    type=self.INPUT_KEYBOARD,
                    union=self._INPUTUNION(
                        ki=self._KEYBDINPUT(
                            wVk=0,  # Virtual key code (ignored for unicode)
                            wScan=unicode_val,  # Unicode character
                            dwFlags=0x0004,  # KEYEVENTF_UNICODE
                            time=0,
                            dwExtraInfo=0,
                        )
                    ),
                )

                # Create unicode key event (up)
                input_obj_up = self._INPUT(
                    type=self.INPUT_KEYBOARD,
                    union=self._INPUTUNION(
                        ki=self._KEYBDINPUT(
                            wVk=0,  # Virtual key code (ignored for unicode)
                            wScan=unicode_val,  # Unicode character
                            dwFlags=0x0004 | 0x0002,  # KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                            time=0,
                            dwExtraInfo=0,
                        )
                    ),
                )

                # Send key down
                input_array_down = self._INPUT_ARRAY(input_obj_down)
                sent_down = self._send_input(1, input_array_down, ctypes.sizeof(self._INPUT))
                if sent_down != 1:
                    return False

                # Send key up
                input_array_up = self._INPUT_ARRAY(input_obj_up)
                sent_up = self._send_input(1, input_array_up, ctypes.sizeof(self._INPUT))
                if sent_up != 1:
                    return False

            return True

        except Exception as e:
            print(f"Failed to type text via Unicode SendInput: {e}")
            return False

    def get_failure_reason(self) -> Optional[str]:
        """Get reason if backend is unavailable."""
        return self._failure_reason

    def _release_all_keys(self):
        """Release any currently held keys."""
        for logical in list(self._held_keys):
            try:
                vk_code = self.get_windows_vk(logical)
                if vk_code is not None:
                    self._send_key_event(vk_code, key_up=True)
            except Exception as e:
                print(f"Error releasing key '{logical}': {e}")
        self._held_keys.clear()
