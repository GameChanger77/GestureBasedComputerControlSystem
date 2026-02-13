import queue
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
        self._avg_latency_ms = None
        self._p95_latency_ms = None
        self._frame_capture_ts_ns = None
        self._pending_latency_origin_ts_ns = None

        # Async action worker keeps OS calls off tracker thread.
        self._action_queue = queue.Queue(maxsize=256)
        self._worker_stop = threading.Event()
        self._worker = threading.Thread(target=self._action_worker, daemon=True)
        self._worker.start()

    def _action_worker(self):
        """Execute queued OS actions off the tracker thread."""
        while not self._worker_stop.is_set():
            try:
                fn, args, origin_ns = self._action_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if fn is None:
                self._action_queue.task_done()
                break

            try:
                fn(*args)
            except Exception as exc:
                print(f"Error executing queued action: {exc}")
            finally:
                if origin_ns is not None:
                    self._record_action_latency(origin_ns=origin_ns)
                self._action_queue.task_done()

    def _enqueue_action(self, fn, args=(), origin_ns=None, drop_if_full=False):
        """Queue an action for background execution."""
        item = (fn, args, origin_ns)
        try:
            self._action_queue.put_nowait(item)
            return True
        except queue.Full:
            if drop_if_full:
                return False
        try:
            self._action_queue.put(item, timeout=0.05)
            return True
        except queue.Full:
            return False

    def _capture_latency_origin_for_action(self):
        """Capture and consume current latency origin for a queued action."""
        with self._latency_lock:
            origin_ns = self._pending_latency_origin_ts_ns or self._frame_capture_ts_ns
            self._pending_latency_origin_ts_ns = None
            return origin_ns

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

    def _record_action_latency(self, origin_ns=None):
        """Record end-to-end action latency sample in ms."""
        now_ns = time.perf_counter_ns()
        with self._latency_lock:
            if origin_ns is None:
                origin_ns = self._pending_latency_origin_ts_ns or self._frame_capture_ts_ns
                self._pending_latency_origin_ts_ns = None
            if origin_ns is None:
                return

            latency_ms = (now_ns - origin_ns) / 1_000_000.0
            if latency_ms < 0:
                return

            self._latency_samples_ms.append(latency_ms)
            self._latest_latency_ms = latency_ms

            samples = list(self._latency_samples_ms)
            self._avg_latency_ms = sum(samples) / len(samples)
            sorted_samples = sorted(samples)
            p95_index = max(0, int(0.95 * len(sorted_samples)) - 1)
            self._p95_latency_ms = sorted_samples[p95_index]

    def get_latency_stats(self):
        """
        Get rolling action latency statistics.

        Returns:
            dict with avg_ms, latest_ms, p95_ms, count
        """
        with self._latency_lock:
            return {
                "avg_ms": self._avg_latency_ms,
                "latest_ms": self._latest_latency_ms,
                "p95_ms": self._p95_latency_ms,
                "count": len(self._latency_samples_ms),
            }

    def _set_mouse_position(self, x: int, y: int):
        self.mouse.position = (int(x), int(y))

    def _left_click_impl(self, x=None, y=None):
        if x is not None and y is not None:
            self._set_mouse_position(x, y)
        self.mouse.click(Button.left, 1)

    def _double_click_impl(self, x=None, y=None):
        if x is not None and y is not None:
            self._set_mouse_position(x, y)
        self.mouse.click(Button.left, 2)

    def _right_click_impl(self, x=None, y=None):
        if x is not None and y is not None:
            self._set_mouse_position(x, y)
        self.mouse.click(Button.right, 1)

    def _scroll_impl(self, delta_x, delta_y):
        self.mouse.scroll(int(delta_x), int(delta_y))

    def move_cursor(self, x: int, y: int):
        """
        Public method to move the cursor.
        Called directly by gesture recognizers.
        """
        origin_ns = self._capture_latency_origin_for_action()
        # Movement can be high-frequency; dropping stale updates avoids queue backpressure.
        self._enqueue_action(
            self._set_mouse_position,
            (int(x), int(y)),
            origin_ns=origin_ns,
            drop_if_full=True,
        )

    def left_click(self, x: int = None, y: int = None):
        """
        Public method to perform left click.
        Called directly by gesture recognizers.
        """
        origin_ns = self._capture_latency_origin_for_action()
        self._enqueue_action(self._left_click_impl, (x, y), origin_ns=origin_ns)

    def double_click(self, x: int = None, y: int = None):
        """
        Public method to perform double click.
        Called directly by gesture recognizers.
        """
        origin_ns = self._capture_latency_origin_for_action()
        self._enqueue_action(self._double_click_impl, (x, y), origin_ns=origin_ns)

    def right_click(self, x: int = None, y: int = None):
        """
        Public method to perform right click.
        Called directly by gesture recognizers.
        """
        origin_ns = self._capture_latency_origin_for_action()
        self._enqueue_action(self._right_click_impl, (x, y), origin_ns=origin_ns)

    def scroll(self, delta_x: int = 0, delta_y: int = 0):
        """
        Public method to perform scroll.
        Called directly by gesture recognizers.
        """
        dx = int(delta_x)
        dy = int(delta_y)
        if dx == 0 and dy == 0:
            return
        origin_ns = self._capture_latency_origin_for_action()
        self._enqueue_action(self._scroll_impl, (dx, dy), origin_ns=origin_ns)

    def hold_left_click(self):
        self._enqueue_action(self.mouse.press, (Button.left,))

    def release_left_click(self):
        self._enqueue_action(self.mouse.release, (Button.left,))

    def hold_right_click(self):
        self._enqueue_action(self.mouse.press, (Button.right,))

    def release_right_click(self):
        self._enqueue_action(self.mouse.release, (Button.right,))

    def press_key(self, key):
        self._enqueue_action(self.keyboard.press, (key,))

    def release_key(self, key):
        self._enqueue_action(self.keyboard.release, (key,))

    def press_and_release_key(self, key):
        self.press_key(key)
        self.release_key(key)

    def perform_macro(self, keys: list):
        for key in keys:
            self.press_and_release_key(key)

    def close(self):
        """Stop background action worker."""
        if self._worker_stop.is_set():
            return
        self._worker_stop.set()
        try:
            self._action_queue.put_nowait((None, (), None))
        except queue.Full:
            pass
        if self._worker.is_alive():
            self._worker.join(timeout=0.25)
