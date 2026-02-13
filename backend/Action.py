import platform
import sys
import time
import threading
from collections import deque

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

else:
    print(f"WARNING: OS '{OS_TYPE}' may not be fully supported. Falling back to basic controls.")


class Action:
    def __init__(self, osType):
        print(f"Action class initialized for {OS_TYPE}")
        self.osType = osType
        self.detected_os = OS_TYPE

        # Latency tracking (capture -> action completion)
        self._latency_lock = threading.Lock()
        self._latency_samples_ms = deque(maxlen=120)
        self._latest_latency_ms = None
        self._frame_capture_ts_ns = None
        self._pending_latency_origin_ts_ns = None

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
                self._record_action_latency()
                return True

            elif action == "left_click":
                x, y = data
                self._click(x, y)
                self._record_action_latency()
                return True

            else:
                print(f"Unknown action: {action}")
                return False

        except Exception as e:
            print(f"Error executing action {action}: {e}")
            return False

    def set_frame_capture_ts_ns(self, ts_ns):
        """Set current frame capture timestamp (ns)."""
        with self._latency_lock:
            self._frame_capture_ts_ns = ts_ns

    def set_pending_latency_origin_ts_ns(self, ts_ns):
        """Set action latency origin for a pending/active gesture (ns)."""
        if ts_ns is None:
            return

        with self._latency_lock:
            self._pending_latency_origin_ts_ns = ts_ns

    def _record_action_latency(self):
        """Record end-to-end action latency sample in ms."""
        now_ns = time.perf_counter_ns()

        with self._latency_lock:
            origin_ns = self._pending_latency_origin_ts_ns or self._frame_capture_ts_ns
            self._pending_latency_origin_ts_ns = None

            if origin_ns is None:
                return

            latency_ms = (now_ns - origin_ns) / 1_000_000.0
            if latency_ms < 0:
                return

            self._latency_samples_ms.append(latency_ms)
            self._latest_latency_ms = latency_ms

    def get_latency_stats(self):
        """
        Get rolling action latency statistics.

        Returns:
            dict with avg_ms, latest_ms, p95_ms, count
        """
        with self._latency_lock:
            samples = list(self._latency_samples_ms)
            latest = self._latest_latency_ms

        if not samples:
            return {
                "avg_ms": None,
                "latest_ms": None,
                "p95_ms": None,
                "count": 0
            }

        avg_ms = sum(samples) / len(samples)
        sorted_samples = sorted(samples)
        p95_index = max(0, int(0.95 * len(sorted_samples)) - 1)
        p95_ms = sorted_samples[p95_index]

        return {
            "avg_ms": avg_ms,
            "latest_ms": latest,
            "p95_ms": p95_ms,
            "count": len(samples)
        }

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
        self._record_action_latency()

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
            self._record_action_latency()
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
            time.sleep(0.05)  # 50ms delay between clicks
            self._click(x, y)
            self._record_action_latency()
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
            self._record_action_latency()
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
        if delta_x != 0 or delta_y != 0:
            self._record_action_latency()
