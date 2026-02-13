import threading
import time
from collections import deque

from pynput.keyboard import Controller as Keyboard
from pynput.mouse import Button, Controller as Mouse


class Action:
    def __init__(self, osType=None):
        # osType kept for backward compatibility with older call sites.
        self.osType = osType
        self.mouse = Mouse()
        self.keyboard = Keyboard()

        # Latency tracking (capture -> action completion)
        self._latency_lock = threading.Lock()
        self._latency_samples_ms = deque(maxlen=120)
        self._latest_latency_ms = None
        self._frame_capture_ts_ns = None
        self._pending_latency_origin_ts_ns = None

    def takeAction(self, action, data):
        """
        Legacy action dispatcher.

        Args:
            action: Action name (mouse_move, left_click, right_click, scroll)
            data: Action payload tuple.
        """
        if action is None:
            return False

        try:
            if action == "mouse_move":
                x, y = data
                self.move_cursor(x, y)
                return True

            if action == "left_click":
                x, y = data
                self.left_click(x, y)
                return True

            if action == "right_click":
                x, y = data
                self.right_click(x, y)
                return True

            if action == "scroll":
                if isinstance(data, (tuple, list)) and len(data) == 2:
                    dx, dy = data
                else:
                    dx, dy = 0, data
                self.scroll(dx, dy)
                return True

            if action == "double_click":
                x, y = data
                self.double_click(x, y)
                return True

            print(f"Unknown action: {action}")
            return False
        except Exception as exc:
            print(f"Error executing action {action}: {exc}")
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
                "count": 0,
            }

        avg_ms = sum(samples) / len(samples)
        sorted_samples = sorted(samples)
        p95_index = max(0, int(0.95 * len(sorted_samples)) - 1)
        p95_ms = sorted_samples[p95_index]

        return {
            "avg_ms": avg_ms,
            "latest_ms": latest,
            "p95_ms": p95_ms,
            "count": len(samples),
        }

    def _set_mouse_position(self, x: int, y: int):
        self.mouse.position = (int(x), int(y))

    def move_cursor(self, x: int, y: int):
        """
        Public method to move the cursor.
        Called directly by gesture recognizers.
        """
        self._set_mouse_position(x, y)
        self._record_action_latency()

    def left_click(self, x: int = None, y: int = None):
        """
        Public method to perform left click.
        Called directly by gesture recognizers.
        """
        if x is not None and y is not None:
            self._set_mouse_position(x, y)
        self.mouse.click(Button.left, 1)
        self._record_action_latency()

    def double_click(self, x: int = None, y: int = None):
        """
        Public method to perform double click.
        Called directly by gesture recognizers.
        """
        if x is not None and y is not None:
            self._set_mouse_position(x, y)
        self.mouse.click(Button.left, 2)
        self._record_action_latency()

    def right_click(self, x: int = None, y: int = None):
        """
        Public method to perform right click.
        Called directly by gesture recognizers.
        """
        if x is not None and y is not None:
            self._set_mouse_position(x, y)
        self.mouse.click(Button.right, 1)
        self._record_action_latency()

    def scroll(self, delta_x: int = 0, delta_y: int = 0):
        """
        Public method to perform scroll.
        Called directly by gesture recognizers.
        """
        dx = int(delta_x)
        dy = int(delta_y)
        self.mouse.scroll(dx, dy)
        if dx != 0 or dy != 0:
            self._record_action_latency()

    def hold_left_click(self):
        self.mouse.press(Button.left)

    def release_left_click(self):
        self.mouse.release(Button.left)

    def hold_right_click(self):
        self.mouse.press(Button.right)

    def release_right_click(self):
        self.mouse.release(Button.right)

    def press_key(self, key):
        self.keyboard.press(key)

    def release_key(self, key):
        self.keyboard.release(key)

    def press_and_release_key(self, key):
        self.press_key(key)
        self.release_key(key)

    def perform_macro(self, keys: list):
        for key in keys:
            self.press_and_release_key(key)
