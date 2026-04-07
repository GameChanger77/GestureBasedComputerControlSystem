"""
macOS-specific keyboard input backend using native Quartz APIs.

Uses Quartz (Core Graphics) and Accessibility framework for reliable
keyboard injection and text input without requiring special permissions.
"""

import time
from typing import List, Optional

from backend.platforms.PlatformKeyboardBackend import PlatformKeyboardBackend
from backend.gestures.keyboard_mode.KeyCodes import normalize_key

# Try to import macOS-specific frameworks
try:
    from Quartz import CGEventCreateKeyboardEvent, CGEventPost, kCGHIDEventTap, kCGKeyDown, kCGKeyUp
    from AppKit import NSPasteboard, NSPasteboardTypeString, NSEvent, NSKeyDown, NSKeyUp, NSFlagsChanged
    MACOS_FRAMEWORKS_AVAILABLE = True
except ImportError:
    MACOS_FRAMEWORKS_AVAILABLE = False


class MacOSKeyboardBackend(PlatformKeyboardBackend):
    """macOS keyboard backend using Quartz framework."""

    # Virtual key codes for macOS (from <Carbon/Carbon.h>)
    LOGICAL_TO_MACOS = {
        "a": 0x00, "b": 0x0B, "c": 0x08, "d": 0x02, "e": 0x0E, "f": 0x03, "g": 0x05,
        "h": 0x04, "i": 0x22, "j": 0x26, "k": 0x28, "l": 0x25, "m": 0x2E, "n": 0x2D,
        "o": 0x1F, "p": 0x23, "q": 0x0C, "r": 0x0F, "s": 0x01, "t": 0x11, "u": 0x20,
        "v": 0x09, "w": 0x0D, "x": 0x07, "y": 0x10, "z": 0x06,
        "0": 0x1D, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "5": 0x17,
        "6": 0x16, "7": 0x1A, "8": 0x1C, "9": 0x19,
        "backtick": 0x32,
        "minus": 0x1B,
        "equals": 0x18,
        "left_bracket": 0x21,
        "right_bracket": 0x1E,
        "backslash": 0x2A,
        "semicolon": 0x29,
        "quote": 0x27,
        "comma": 0x2B,
        "period": 0x2F,
        "slash": 0x2C,
        "space": 0x31,
        "tab": 0x30,
        "enter": 0x24,
        "backspace": 0x33,
        "escape": 0x35,
        "delete": 0x75,
        "left_ctrl": 0x3B,
        "right_ctrl": 0x3E,
        "left_shift": 0x38,
        "right_shift": 0x3C,
        "left_alt": 0x3A,
        "right_alt": 0x3D,
        "left_win": 0x37,
        "right_win": 0x36,  # Right Command
        "left_cmd": 0x37,
        "right_cmd": 0x36,
        "arrow_up": 0x7E,
        "arrow_down": 0x7D,
        "arrow_left": 0x7B,
        "arrow_right": 0x7C,
        "home": 0x73,
        "end": 0x77,
        "page_up": 0x74,
        "page_down": 0x79,
        "insert": 0x72,
        "caps_lock": 0x39,
        "num_lock": 0x47,
        "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60,
        "f6": 0x61, "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D,
        "f11": 0x67, "f12": 0x6F,
    }

    # Modifier key codes for macOS
    MAC_MOD_SHIFT = 1 << 17
    MAC_MOD_CTRL = 1 << 18
    MAC_MOD_ALT = 1 << 19
    MAC_MOD_CMD = 1 << 20

    def __init__(self):
        self._failure_reason = None
        self._held_keys = set()
        self._frameworks_available = MACOS_FRAMEWORKS_AVAILABLE

    @staticmethod
    def get_macos_vk_static(key_code: str) -> Optional[int]:
        """Static method to get Windows VK code for a logical key id."""
        key = normalize_key(key_code)
        return MacOSKeyboardBackend.LOGICAL_TO_MACOS.get(key)

    def initialize(self) -> bool:
        """Initialize macOS keyboard backend."""
        if not self._frameworks_available:
            self._failure_reason = (
                "macOS Quartz framework not available. "
                "Please ensure PyObjC is installed: pip install pyobjc-framework-ApplicationServices"
            )
            return False
        return True

    def shutdown(self):
        """Clean up resources."""
        self._release_all_keys()

    def is_available(self) -> bool:
        """Check if backend is available."""
        return self._frameworks_available

    def _get_modifier_flags(self, logical_keys: List[str]) -> int:
        """Calculate modifier flags for a list of keys."""
        flags = 0
        for logical in logical_keys:
            if logical == "left_shift" or logical == "right_shift":
                flags |= self.MAC_MOD_SHIFT
            elif logical == "left_ctrl" or logical == "right_ctrl":
                flags |= self.MAC_MOD_CTRL
            elif logical == "left_alt" or logical == "right_alt":
                flags |= self.MAC_MOD_ALT
            elif logical == "left_win" or logical == "right_win" or logical == "left_cmd" or logical == "right_cmd":
                flags |= self.MAC_MOD_CMD
        return flags

    def _send_key_event(self, vk_code: int, key_down: bool, flags: int = 0) -> bool:
        """
        Send a key event using Quartz.

        Args:
            vk_code: Virtual key code for macOS
            key_down: True for key down, False for key up
            flags: Modifier flags

        Returns:
            True if successful, False otherwise.
        """
        try:
            event_type = kCGKeyDown if key_down else kCGKeyUp
            event = CGEventCreateKeyboardEvent(None, vk_code, key_down)
            if event is None:
                return False

            # Set modifier flags
            if flags:
                event.setIntegerValueForField_(flags, 1)  # Field 1 is flags

            CGEventPost(kCGHIDEventTap, event)
            return True
        except Exception as e:
            print(f"Error sending key event via Quartz: {e}")
            return False

    def key_down(self, key_code: str) -> bool:
        """Press and hold a key."""
        logical = normalize_key(key_code)
        if not logical or logical in self._held_keys:
            return False

        vk_code = self.MAC_VK_CODES.get(logical)
        if vk_code is None:
            return False

        if self._send_key_event(vk_code, key_down=True):
            self._held_keys.add(logical)
            return True
        return False

    def key_up(self, key_code: str) -> bool:
        """Release a held key."""
        logical = normalize_key(key_code)
        if not logical:
            return False

        vk_code = self.MAC_VK_CODES.get(logical)
        if vk_code is None:
            return False

        result = self._send_key_event(vk_code, key_down=False)
        self._held_keys.discard(logical)
        return result

    def tap_key(self, key_code: str) -> bool:
        """Press and release a key."""
        logical = normalize_key(key_code)
        if not logical:
            return False

        vk_code = self.MAC_VK_CODES.get(logical)
        if vk_code is None:
            return False

        return self._send_key_event(vk_code, key_down=True) and self._send_key_event(vk_code, key_down=False)

    def tap_hotkey(self, key_codes: List[str]) -> bool:
        """Press multiple keys together as a hotkey."""
        if not key_codes:
            return False

        logical_keys = [normalize_key(k) for k in key_codes]
        if not all(logical_keys):
            return False

        vk_codes = []
        for logical in logical_keys:
            vk = self.MAC_VK_CODES.get(logical)
            if vk is None:
                return False
            vk_codes.append((logical, vk))

        flags = self._get_modifier_flags(logical_keys)

        # Press all keys
        for logical, vk_code in vk_codes:
            if not self._send_key_event(vk_code, key_down=True, flags=flags):
                # Release already-pressed keys on failure
                for prev_logical, prev_vk in vk_codes[:vk_codes.index((logical, vk_code))]:
                    self._send_key_event(prev_vk, key_down=False, flags=flags)
                return False

        # Release all keys in reverse order
        success = True
        for logical, vk_code in reversed(vk_codes):
            if not self._send_key_event(vk_code, key_down=False, flags=flags):
                success = False

        # Clear held keys tracking
        for logical, _ in vk_codes:
            self._held_keys.discard(logical)

        return success

    def type_text(self, text: str) -> bool:
        """
        Type text using the pasteboard (clipboard).

        This is more reliable than character-by-character input on macOS,
        especially for special characters and international input.
        """
        if not text:
            return False

        try:
            # Copy text to pasteboard
            pasteboard = NSPasteboard.generalPasteboard()
            pasteboard.clearContents()
            pasteboard.setString_forType_(text, NSPasteboardTypeString)

            # Paste using Cmd+V
            time.sleep(0.01)
            return self.tap_hotkey(["left_win", "v"])  # Cmd+V
        except Exception as e:
            print(f"Error typing text via pasteboard: {e}")
            return False

    def get_failure_reason(self) -> Optional[str]:
        """Get reason if backend is unavailable."""
        return self._failure_reason

    def _release_all_keys(self):
        """Release any currently held keys."""
        for logical in list(self._held_keys):
            try:
                vk_code = self.MAC_VK_CODES.get(logical)
                if vk_code is not None:
                    self._send_key_event(vk_code, key_down=False)
            except Exception as e:
                print(f"Error releasing key '{logical}': {e}")
        self._held_keys.clear()

