import platform
import sys
import time

from backend.keyboard.KeyCodes import get_windows_vk, normalize_key

# Detect OS and import appropriate libraries
OS_TYPE = platform.system()

if OS_TYPE == "Darwin":  # macOS
    try:
        from Quartz import (
            CGEventCreateMouseEvent,
            CGEventPost,
            CGEventCreateScrollWheelEvent,
            kCGHIDEventTap,
            kCGEventMouseMoved,
            kCGEventLeftMouseDown,
            kCGEventLeftMouseUp,
            kCGEventRightMouseDown,
            kCGEventRightMouseUp,
            kCGScrollEventUnitPixel
        )
    except ImportError:
        print("ERROR: pyobjc-framework-Quartz not installed. Run: pip install pyobjc-framework-Quartz")
        sys.exit(1)

elif OS_TYPE == "Windows":
    import ctypes
    from ctypes import wintypes

else:
    print(f"WARNING: OS '{OS_TYPE}' may not be fully supported. Falling back to basic controls.")


class Action:
    def __init__(self, osType=None):
        print(f"Action class initialized for {OS_TYPE}")
        self.osType = osType if osType is not None else OS_TYPE
        self.detected_os = OS_TYPE
        self._held_keys = set()
        self._unsupported_keyboard_warned = False
        self._keyboard_send_failures = 0
        self._keyboard_disabled = False

        if self.detected_os == "Windows":
            self._init_windows_keyboard_structs()

    def _init_windows_keyboard_structs(self):
        """Create ctypes structures for SendInput keyboard injection."""
        self.INPUT_KEYBOARD = 1
        self.KEYEVENTF_KEYUP = 0x0002
        self.KEYEVENTF_EXTENDEDKEY = 0x0001
        self._MAX_CONSECUTIVE_SEND_FAILS = 10

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
        self._send_input.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        self._send_input.restype = wintypes.UINT

        self._get_last_error = ctypes.windll.kernel32.GetLastError
        self._get_last_error.argtypes = ()
        self._get_last_error.restype = wintypes.DWORD

        self._MOUSEINPUT = MOUSEINPUT
        self._KEYBDINPUT = KEYBDINPUT
        self._HARDWAREINPUT = HARDWAREINPUT
        self._INPUTUNION = _INPUTUNION
        self._INPUT = INPUT

    def takeAction(self, action, data):
        """
        Takes in a string which is an action to execute on the operating system.
        The data is information that is necessary to complete that action.

        Args:
            action: the action to take (mouse_move, left_click, etc.)
            data: a tuple whose contents depend on the action taken.

        Returns:
            bool: True if action was successful, False otherwise
        """
        if action is None:
            return False

        try:
            if action == "mouse_move":
                x, y = data
                self._move_cursor(x, y)
                return True

            elif action == "left_click":
                x, y = data
                self._click(x, y)
                return True

            else:
                print(f"Unknown action: {action}")
                return False

        except Exception as e:
            print(f"Error executing action {action}: {e}")
            return False

    def _move_cursor(self, x: int, y: int):
        """
        Move cursor using native OS API (auto-detects OS).
        """
        if self.detected_os == "Darwin":
            self._move_cursor_macos(x, y)
        elif self.detected_os == "Windows":
            self._move_cursor_windows(x, y)
        else:
            print(f"Mouse movement not implemented for {self.detected_os}")

    def _click(self, x: int, y: int):
        """
        Perform left mouse click using native OS API (auto-detects OS).
        """
        if self.detected_os == "Darwin":
            self._click_macos(x, y)
        elif self.detected_os == "Windows":
            self._click_windows(x, y)
        else:
            print(f"Mouse click not implemented for {self.detected_os}")

    def _right_click(self, x: int, y: int):
        """
        Perform right mouse click using native OS API (auto-detects OS).
        """
        if self.detected_os == "Darwin":
            self._right_click_macos(x, y)
        elif self.detected_os == "Windows":
            self._right_click_windows(x, y)
        else:
            print(f"Right click not implemented for {self.detected_os}")

    def _scroll(self, delta_x: int, delta_y: int):
        """
        Perform scroll using native OS API (auto-detects OS).
        """
        if self.detected_os == "Darwin":
            self._scroll_macos(delta_x, delta_y)
        elif self.detected_os == "Windows":
            self._scroll_windows(delta_x, delta_y)
        else:
            print(f"Scroll not implemented for {self.detected_os}")

    # ==================== macOS Implementation ====================

    def _move_cursor_macos(self, x: int, y: int):
        """
        Move cursor on macOS using native Quartz API.
        This is 10-50x faster than PyAutoGUI (~1ms vs 100-200ms).
        """
        event = CGEventCreateMouseEvent(
            None,
            kCGEventMouseMoved,
            (x, y),
            0
        )
        CGEventPost(kCGHIDEventTap, event)

    def _click_macos(self, x: int, y: int):
        """
        Perform left mouse click on macOS using native Quartz API.
        """
        # Move to position first
        self._move_cursor_macos(x, y)

        # Create mouse down event
        down_event = CGEventCreateMouseEvent(
            None,
            kCGEventLeftMouseDown,
            (x, y),
            0
        )

        # Create mouse up event
        up_event = CGEventCreateMouseEvent(
            None,
            kCGEventLeftMouseUp,
            (x, y),
            0
        )

        # Post both events to simulate a click
        CGEventPost(kCGHIDEventTap, down_event)
        CGEventPost(kCGHIDEventTap, up_event)

    def _right_click_macos(self, x: int, y: int):
        """
        Perform right mouse click on macOS using native Quartz API.
        """
        # Move to position first
        self._move_cursor_macos(x, y)

        # Create right mouse down event
        down_event = CGEventCreateMouseEvent(
            None,
            kCGEventRightMouseDown,
            (x, y),
            0
        )

        # Create right mouse up event
        up_event = CGEventCreateMouseEvent(
            None,
            kCGEventRightMouseUp,
            (x, y),
            0
        )

        # Post both events to simulate a right click
        CGEventPost(kCGHIDEventTap, down_event)
        CGEventPost(kCGHIDEventTap, up_event)

    def _scroll_macos(self, delta_x: int, delta_y: int):
        """
        Perform scroll on macOS using native Quartz API.

        Args:
            delta_x: Horizontal scroll amount (positive = right, negative = left)
            delta_y: Vertical scroll amount (positive = up, negative = down)
        """
        # Create scroll event
        scroll_event = CGEventCreateScrollWheelEvent(
            None,
            kCGScrollEventUnitPixel,
            2,  # Number of wheels (2 for x and y)
            int(delta_y),
            int(delta_x)
        )

        # Post the scroll event
        CGEventPost(kCGHIDEventTap, scroll_event)

    # ==================== Windows Implementation ====================

    def _move_cursor_windows(self, x: int, y: int):
        """
        Move cursor on Windows using native Win32 API.
        This is 10-50x faster than PyAutoGUI.
        """
        ctypes.windll.user32.SetCursorPos(x, y)

    def _click_windows(self, x: int, y: int):
        """
        Perform left mouse click on Windows using native Win32 API.
        """
        # Move to position first
        self._move_cursor_windows(x, y)

        # Mouse event constants
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004

        # Perform click (down then up)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, x, y, 0, 0)

    def _right_click_windows(self, x: int, y: int):
        """
        Perform right mouse click on Windows using native Win32 API.
        """
        # Move to position first
        self._move_cursor_windows(x, y)

        # Mouse event constants
        MOUSEEVENTF_RIGHTDOWN = 0x0008
        MOUSEEVENTF_RIGHTUP = 0x0010

        # Perform right click (down then up)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, x, y, 0, 0)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTUP, x, y, 0, 0)

    def _scroll_windows(self, delta_x: int, delta_y: int):
        """
        Perform scroll on Windows using native Win32 API.

        Args:
            delta_x: Horizontal scroll amount (positive = right, negative = left)
            delta_y: Vertical scroll amount (positive = up, negative = down)
        """
        # Mouse event constants
        MOUSEEVENTF_WHEEL = 0x0800
        MOUSEEVENTF_HWHEEL = 0x01000

        # Windows uses WHEEL_DELTA (120) as one "click" of the wheel
        WHEEL_DELTA = 120

        # Vertical scroll
        if delta_y != 0:
            ctypes.windll.user32.mouse_event(
                MOUSEEVENTF_WHEEL, 0, 0, int(delta_y * WHEEL_DELTA), 0
            )

        # Horizontal scroll
        if delta_x != 0:
            ctypes.windll.user32.mouse_event(
                MOUSEEVENTF_HWHEEL, 0, 0, int(delta_x * WHEEL_DELTA), 0
            )

    # ==================== Keyboard Injection (Windows-first) ====================

    def _send_key_event_windows(self, vk_code: int, key_up: bool = False):
        """Send one key event via Windows SendInput."""
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

        sent = self._send_input(1, ctypes.byref(input_obj), ctypes.sizeof(self._INPUT))
        if sent != 1:
            self._keyboard_send_failures += 1
            if self._keyboard_send_failures == 1:
                err = self._get_last_error()
                print(f"Keyboard SendInput failed (vk={vk_code}, key_up={key_up}, winerr={err})")
            if self._keyboard_send_failures >= self._MAX_CONSECUTIVE_SEND_FAILS:
                self._keyboard_disabled = True
                print("Keyboard input disabled after repeated SendInput failures")
            return False

        self._keyboard_send_failures = 0
        return True

    def _key_down_windows(self, key_code: str):
        vk_code = get_windows_vk(key_code)
        if vk_code is None:
            print(f"Warning: unsupported key code '{key_code}' for Windows")
            return False
        return self._send_key_event_windows(vk_code, key_up=False)

    def _key_up_windows(self, key_code: str):
        vk_code = get_windows_vk(key_code)
        if vk_code is None:
            return False
        return self._send_key_event_windows(vk_code, key_up=True)

    def _warn_keyboard_not_supported(self):
        if not self._unsupported_keyboard_warned:
            print(f"Keyboard injection not implemented for {self.detected_os} yet")
            self._unsupported_keyboard_warned = True

    def _key_down_macos(self, key_code: str):
        self._warn_keyboard_not_supported()

    def _key_up_macos(self, key_code: str):
        self._warn_keyboard_not_supported()

    def _key_down_linux(self, key_code: str):
        self._warn_keyboard_not_supported()

    def _key_up_linux(self, key_code: str):
        self._warn_keyboard_not_supported()

    def _key_down(self, key_code: str):
        if self.detected_os == "Windows":
            return self._key_down_windows(key_code)
        elif self.detected_os == "Darwin":
            self._key_down_macos(key_code)
            return False
        elif self.detected_os == "Linux":
            self._key_down_linux(key_code)
            return False
        else:
            self._warn_keyboard_not_supported()
            return False

    def _key_up(self, key_code: str):
        if self.detected_os == "Windows":
            return self._key_up_windows(key_code)
        elif self.detected_os == "Darwin":
            self._key_up_macos(key_code)
            return False
        elif self.detected_os == "Linux":
            self._key_up_linux(key_code)
            return False
        else:
            self._warn_keyboard_not_supported()
            return False

    # ==================== Public API for Gesture Recognizers ====================

    def move_cursor(self, x: int, y: int):
        """
        Public method to move the cursor.
        Called directly by gesture recognizers.

        Args:
            x: Screen x coordinate in pixels
            y: Screen y coordinate in pixels
        """
        self._move_cursor(x, y)

    def left_click(self, x: int = None, y: int = None):
        """
        Public method to perform left click.
        Called directly by gesture recognizers.

        Args:
            x: Screen x coordinate in pixels (optional, uses current position if not provided)
            y: Screen y coordinate in pixels (optional, uses current position if not provided)
        """
        if x is not None and y is not None:
            self._click(x, y)
        else:
            # Click at current cursor position
            # For simplicity, we'll require coordinates for now
            print("Warning: left_click requires x, y coordinates")

    def double_click(self, x: int = None, y: int = None):
        """
        Public method to perform double click.
        Called directly by gesture recognizers.

        Args:
            x: Screen x coordinate in pixels
            y: Screen y coordinate in pixels
        """
        if x is not None and y is not None:
            # Perform two clicks in quick succession
            self._click(x, y)
            import time
            time.sleep(0.05)  # 50ms delay between clicks
            self._click(x, y)
        else:
            print("Warning: double_click requires x, y coordinates")

    def right_click(self, x: int = None, y: int = None):
        """
        Public method to perform right click.
        Called directly by gesture recognizers.

        Args:
            x: Screen x coordinate in pixels (optional, uses current position if not provided)
            y: Screen y coordinate in pixels (optional, uses current position if not provided)
        """
        if x is not None and y is not None:
            self._right_click(x, y)
        else:
            # Right click at current cursor position
            # For simplicity, we'll require coordinates for now
            print("Warning: right_click requires x, y coordinates")

    def scroll(self, delta_x: int = 0, delta_y: int = 0):
        """
        Public method to perform scroll.
        Called directly by gesture recognizers.

        Args:
            delta_x: Horizontal scroll amount (positive = right, negative = left)
            delta_y: Vertical scroll amount (positive = up, negative = down)
        """
        self._scroll(delta_x, delta_y)

    def key_down(self, key_code: str):
        """
        Press and hold a keyboard key.

        Args:
            key_code: Logical key id (e.g. 'a', 'left_ctrl', 'enter')
        """
        logical = normalize_key(key_code)
        if not logical:
            return
        if logical in self._held_keys:
            return

        try:
            if self._key_down(logical):
                self._held_keys.add(logical)
        except Exception as e:
            print(f"Error on key_down('{logical}'): {e}")

    def key_up(self, key_code: str):
        """
        Release a keyboard key.

        Args:
            key_code: Logical key id
        """
        logical = normalize_key(key_code)
        if not logical:
            return

        try:
            self._key_up(logical)
        except Exception as e:
            print(f"Error on key_up('{logical}'): {e}")
        finally:
            self._held_keys.discard(logical)

    def tap_key(self, key_code: str):
        """
        Press and release a key.
        """
        logical = normalize_key(key_code)
        if not logical:
            return

        self.key_down(logical)
        # Keep tap tight but explicit to maintain event ordering.
        time.sleep(0.005)
        self.key_up(logical)

    def release_all_keys(self):
        """
        Release any currently held keys. Used on mode switch/pause/shutdown.
        """
        for key in list(self._held_keys):
            try:
                self._key_up(key)
            except Exception as e:
                print(f"Error releasing key '{key}': {e}")
        self._held_keys.clear()
