"""
macOS-specific keyboard input backend using native Quartz APIs.
"""

from typing import List, Optional

from backend.gestures.keyboard_mode.KeyCodes import normalize_key
from backend.platforms.PlatformKeyboardBackend import PlatformKeyboardBackend

CGEventCreateKeyboardEvent = None
CGEventKeyboardSetUnicodeString = None
CGEventPost = None
CGEventSetFlags = None
kCGHIDEventTap = None
kCGEventFlagMaskShift = 0
kCGEventFlagMaskControl = 0
kCGEventFlagMaskAlternate = 0
kCGEventFlagMaskCommand = 0
QUARTZ_IMPORT_ERROR = None

try:
    from Quartz import (
        CGEventCreateKeyboardEvent,
        CGEventKeyboardSetUnicodeString,
        CGEventPost,
        CGEventSetFlags,
        kCGEventFlagMaskAlternate,
        kCGEventFlagMaskCommand,
        kCGEventFlagMaskControl,
        kCGEventFlagMaskShift,
        kCGHIDEventTap,
    )
except ImportError as exc:
    QUARTZ_IMPORT_ERROR = str(exc)


class MacOSKeyboardBackend(PlatformKeyboardBackend):
    """macOS keyboard backend using Quartz keyboard events."""

    META_KEY_LABEL = "Cmd"

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
        "right_win": 0x36,
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
    KEY_MAPPING = LOGICAL_TO_MACOS
    MODIFIER_FLAG_BY_KEY = {
        "left_shift": kCGEventFlagMaskShift,
        "right_shift": kCGEventFlagMaskShift,
        "left_ctrl": kCGEventFlagMaskControl,
        "right_ctrl": kCGEventFlagMaskControl,
        "left_alt": kCGEventFlagMaskAlternate,
        "right_alt": kCGEventFlagMaskAlternate,
        "left_win": kCGEventFlagMaskCommand,
        "right_win": kCGEventFlagMaskCommand,
        "left_cmd": kCGEventFlagMaskCommand,
        "right_cmd": kCGEventFlagMaskCommand,
    }

    def __init__(self):
        self._failure_reason = None
        self._held_keys = set()
        self._initialized = False
        self._quartz_available = (
            CGEventCreateKeyboardEvent is not None
            and CGEventKeyboardSetUnicodeString is not None
            and CGEventPost is not None
            and CGEventSetFlags is not None
        )

    @staticmethod
    def get_macos_vk_static(key_code: str) -> Optional[int]:
        """Static method to get the macOS virtual key code for a logical key id."""
        key = normalize_key(key_code)
        return MacOSKeyboardBackend.LOGICAL_TO_MACOS.get(key)

    def initialize(self) -> bool:
        """Initialize macOS keyboard backend."""
        if not self._quartz_available:
            self._failure_reason = f"Quartz unavailable: {QUARTZ_IMPORT_ERROR or 'unknown import error'}"
            self._initialized = False
            return False

        self._initialized = True
        self._failure_reason = None
        return True

    def shutdown(self):
        """Clean up resources."""
        self.release_all_keys()
        self._initialized = False

    def is_available(self) -> bool:
        """Check if backend is available."""
        return self._initialized

    def _modifier_flag_for_key(self, logical: str) -> int:
        return self.MODIFIER_FLAG_BY_KEY.get(logical, 0)

    def _current_modifier_flags(self, extra_keys=None, exclude_keys=None) -> int:
        keys = set(self._held_keys)
        if extra_keys:
            keys.update(extra_keys)
        if exclude_keys:
            keys.difference_update(exclude_keys)

        flags = 0
        for logical in keys:
            flags |= self._modifier_flag_for_key(logical)
        return flags

    def _send_key_event(self, vk_code: int, key_down: bool, flags: int = 0) -> bool:
        """Send a key event using Quartz."""
        try:
            event = CGEventCreateKeyboardEvent(None, vk_code, key_down)
            if event is None:
                return False

            CGEventSetFlags(event, flags)
            CGEventPost(kCGHIDEventTap, event)
            return True
        except Exception as exc:
            print(f"Error sending key event via Quartz: {exc}")
            return False

    def _send_unicode_text(self, text: str) -> bool:
        """Inject text directly using Quartz Unicode keyboard events."""
        try:
            for char in text:
                key_down = CGEventCreateKeyboardEvent(None, 0, True)
                key_up = CGEventCreateKeyboardEvent(None, 0, False)
                if key_down is None or key_up is None:
                    return False

                CGEventSetFlags(key_down, 0)
                CGEventSetFlags(key_up, 0)
                CGEventKeyboardSetUnicodeString(key_down, len(char), char)
                CGEventKeyboardSetUnicodeString(key_up, len(char), char)
                CGEventPost(kCGHIDEventTap, key_down)
                CGEventPost(kCGHIDEventTap, key_up)
            return True
        except Exception as exc:
            print(f"Error sending unicode text via Quartz: {exc}")
            return False

    def key_down(self, key_code: str) -> bool:
        """Press and hold a key."""
        logical = normalize_key(key_code)
        if not logical or logical in self._held_keys:
            return False

        vk_code = self.LOGICAL_TO_MACOS.get(logical)
        if vk_code is None:
            return False

        flags = self._current_modifier_flags(extra_keys={logical})
        if self._send_key_event(vk_code, key_down=True, flags=flags):
            self._held_keys.add(logical)
            return True
        return False

    def key_up(self, key_code: str) -> bool:
        """Release a held key."""
        logical = normalize_key(key_code)
        if not logical:
            return False

        vk_code = self.LOGICAL_TO_MACOS.get(logical)
        if vk_code is None:
            return False

        flags = self._current_modifier_flags(exclude_keys={logical})
        result = self._send_key_event(vk_code, key_down=False, flags=flags)
        self._held_keys.discard(logical)
        return result

    def tap_key(self, key_code: str) -> bool:
        """Press and release a key."""
        logical = normalize_key(key_code)
        if not logical:
            return False

        vk_code = self.LOGICAL_TO_MACOS.get(logical)
        if vk_code is None:
            return False

        down_flags = self._current_modifier_flags(extra_keys={logical})
        up_flags = self._current_modifier_flags(exclude_keys={logical})
        return self._send_key_event(vk_code, key_down=True, flags=down_flags) and self._send_key_event(
            vk_code, key_down=False, flags=up_flags
        )

    def tap_hotkey(self, key_codes: List[str]) -> bool:
        """Press modifiers first, then tap non-modifiers, then release modifiers in reverse."""
        if not key_codes:
            return False

        resolved = []
        for key_code in key_codes:
            logical = normalize_key(key_code)
            if not logical:
                return False
            vk_code = self.LOGICAL_TO_MACOS.get(logical)
            if vk_code is None:
                return False
            resolved.append((logical, vk_code))

        modifier_keys = [item for item in resolved if self._modifier_flag_for_key(item[0])]
        regular_keys = [item for item in resolved if not self._modifier_flag_for_key(item[0])]
        pressed_modifiers = []
        active_modifiers = set()

        try:
            for logical, vk_code in modifier_keys:
                active_modifiers.add(logical)
                flags = self._current_modifier_flags(extra_keys=active_modifiers)
                if not self._send_key_event(vk_code, key_down=True, flags=flags):
                    return False
                pressed_modifiers.append((logical, vk_code))

            active_modifier_flags = self._current_modifier_flags(extra_keys=active_modifiers)
            for logical, vk_code in regular_keys:
                if not self._send_key_event(vk_code, key_down=True, flags=active_modifier_flags):
                    return False
                if not self._send_key_event(vk_code, key_down=False, flags=active_modifier_flags):
                    return False

            return True
        finally:
            for logical, vk_code in reversed(pressed_modifiers):
                active_modifiers.discard(logical)
                flags = self._current_modifier_flags(extra_keys=active_modifiers)
                self._send_key_event(vk_code, key_down=False, flags=flags)

    def type_text(self, text: str) -> bool:
        """Type text directly via Quartz Unicode events."""
        if not text:
            return False

        return self._send_unicode_text(text)

    def get_failure_reason(self) -> Optional[str]:
        """Get reason if backend is unavailable."""
        return self._failure_reason

    def release_all_keys(self):
        """Release any currently held keys."""
        for logical in list(self._held_keys):
            try:
                vk_code = self.LOGICAL_TO_MACOS.get(logical)
                if vk_code is not None:
                    flags = self._current_modifier_flags(exclude_keys={logical})
                    self._send_key_event(vk_code, key_down=False, flags=flags)
            except Exception as exc:
                print(f"Error releasing key '{logical}': {exc}")
        self._held_keys.clear()
