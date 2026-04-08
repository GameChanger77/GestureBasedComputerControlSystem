from abc import ABC, abstractmethod
from ctypes import wintypes
import platform
import queue
import threading
import time
from collections import deque
from copy import deepcopy

from backend.macros.macro_models import MacroActionStep
from backend.gestures.keyboard_mode.KeyCodes import normalize_key
from backend.platforms import PlatformKeyboardBackend, create_keyboard_backend, normalize_os_name
from backend.platforms.PynputKeyboardBackend import PynputKeyboardBackend

try:
    from pynput.mouse import Controller as Mouse, Button
    from pynput.keyboard import Controller as Keyboard
except ImportError:
    Mouse = None
    Keyboard = None


    class Button:
        left = "left"
        right = "right"

OS_TYPE = platform.system()


class MouseTest(ABC):
    @abstractmethod
    def move_cursor(self, x: int, y: int):
        pass

    @abstractmethod
    def left_click(self, x: int = None, y: int = None):
        pass

    @abstractmethod
    def double_click(self, x: int = None, y: int = None):
        pass

    @abstractmethod
    def right_click(self, x: int = None, y: int = None):
        pass

    @abstractmethod
    def scroll(self, delta_x: int = 0, delta_y: int = 0):
        pass


class KeyboardTest(ABC):
    @abstractmethod
    def press_key(self, key):
        pass

    @abstractmethod
    def release_key(self, key):
        pass

    @abstractmethod
    def press_and_release_key(self, key):
        pass

    @abstractmethod
    def perform_macro(self, keys: list):
        pass


class Action:

    def __init__(
            self,
            mouse: MouseTest = None,
            keyboard_test: KeyboardTest = None,
            osType=None,
            screen_origin_x: int = 0,
            screen_origin_y: int = 0,
    ):
        if mouse is None and Mouse is None:
            raise RuntimeError("pynput is required for the default mouse controller")
        if keyboard_test is None and Keyboard is None:
            raise RuntimeError("pynput is required for the default keyboard controller")

        self.mouse = mouse if mouse is not None else Mouse()
        self.keyboard = keyboard_test if keyboard_test is not None else Keyboard()
        self.osType = osType if osType is not None else OS_TYPE
        self.screen_origin_x = int(screen_origin_x)
        self.screen_origin_y = int(screen_origin_y)
        self.detected_os = normalize_os_name(self.osType)
        self._keyboard_backend = self._create_keyboard_backend(use_platform_backend=keyboard_test is None)
        self._windows_backend = (
            self._keyboard_backend
            if self.detected_os == "Windows" and hasattr(self._keyboard_backend, "_send_input")
            else None
        )
        self._send_input = getattr(self._keyboard_backend, "_send_input", None)
        if self.detected_os == "Windows" and self._send_input is None:
            self._send_input = self._build_windows_send_input_compat()

        # Latency tracking (capture -> action completion)
        self._latency_lock = threading.Lock()
        self._latency_samples_ms = deque(maxlen=120)
        self._latest_latency_ms = None
        self._avg_latency_ms = None
        self._p95_latency_ms = None
        self._frame_capture_ts_ns = None
        self._pending_latency_origin_ts_ns = None

        # Tutorial support: bounded mouse scope and observable action events.
        self._tutorial_scope_lock = threading.Lock()
        self._tutorial_scope = {
            "bounds": None,
            "capture_text": False,
        }
        self._event_lock = threading.Lock()
        self._event_sequence = 0
        self._recent_action_events = deque(maxlen=512)
        self._cursor_lock = threading.Lock()
        initial_global = self._safe_mouse_position()
        self._last_cursor_global = initial_global
        self._last_cursor_local = (
            int(initial_global[0] - self.screen_origin_x),
            int(initial_global[1] - self.screen_origin_y),
        )
        self._move_generation_lock = threading.Lock()
        self._move_generation = 0

        # Async action worker keeps OS calls off tracker thread.
        self._action_queue = queue.Queue(maxsize=256)
        self._worker_stop = threading.Event()
        self._worker = threading.Thread(target=self._action_worker, daemon=True)
        self._worker.start()

    def _create_keyboard_backend(self, *, use_platform_backend: bool) -> PlatformKeyboardBackend:
        host_os = normalize_os_name()
        if use_platform_backend and self.detected_os == host_os:
            try:
                return create_keyboard_backend(target_os=self.detected_os)
            except Exception as exc:
                print(f"Falling back to local keyboard controller backend: {exc}")

        backend = PynputKeyboardBackend(self.keyboard, self.detected_os)
        backend.initialize()
        return backend

    @staticmethod
    def _build_windows_send_input_compat():
        class _SendInputCompat:
            argtypes = [wintypes.UINT, wintypes.LPVOID, wintypes.INT]

        return _SendInputCompat()

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

    def set_tutorial_scope(self, *, bounds=None, capture_text: bool = False):
        """Clamp mouse actions to a tutorial rect and optionally capture typed text."""
        normalized_bounds = None
        if bounds is not None:
            x, y, width, height = bounds
            normalized_bounds = (
                int(x),
                int(y),
                max(1, int(width)),
                max(1, int(height)),
            )
        with self._tutorial_scope_lock:
            self._tutorial_scope = {
                "bounds": normalized_bounds,
                "capture_text": bool(capture_text),
            }

    def clear_tutorial_scope(self):
        self.set_tutorial_scope(bounds=None, capture_text=False)

    def get_action_events(self, *, after_sequence: int = 0):
        with self._event_lock:
            return [
                deepcopy(event)
                for event in self._recent_action_events
                if int(event.get("sequence", 0)) > int(after_sequence)
            ]

    def _record_action_event(self, event_type: str, **payload):
        with self._event_lock:
            self._event_sequence += 1
            event = {
                "sequence": self._event_sequence,
                "type": str(event_type),
                "timestamp_ns": time.perf_counter_ns(),
            }
            event.update(payload)
            self._recent_action_events.append(event)

    def _safe_mouse_position(self):
        try:
            position = tuple(self.mouse.position)
            if len(position) == 2:
                return int(position[0]), int(position[1])
        except Exception:
            pass
        return int(self.screen_origin_x), int(self.screen_origin_y)

    def _update_committed_cursor_position(self, local_x: int, local_y: int, global_x: int, global_y: int):
        with self._cursor_lock:
            self._last_cursor_local = (int(local_x), int(local_y))
            self._last_cursor_global = (int(global_x), int(global_y))

    def _current_cursor_snapshot(self):
        with self._cursor_lock:
            return {
                "local_x": int(self._last_cursor_local[0]),
                "local_y": int(self._last_cursor_local[1]),
                "global_x": int(self._last_cursor_global[0]),
                "global_y": int(self._last_cursor_global[1]),
            }

    def _invalidate_pending_move_actions(self):
        with self._move_generation_lock:
            self._move_generation += 1
            return self._move_generation

    def _current_move_generation(self):
        with self._move_generation_lock:
            return self._move_generation

    def get_runtime_debug_snapshot(self):
        latest_event = None
        with self._event_lock:
            if self._recent_action_events:
                latest_event = deepcopy(self._recent_action_events[-1])
        snapshot = {
            "cursor": self._current_cursor_snapshot(),
            "latest_action_event": latest_event,
        }
        return snapshot

    def _current_tutorial_scope(self):
        with self._tutorial_scope_lock:
            return dict(self._tutorial_scope)

    def _clamp_mouse_coordinates(self, x: int, y: int):
        scope = self._current_tutorial_scope()
        bounds = scope.get("bounds")
        if bounds is None:
            return int(x), int(y)
        bx, by, bw, bh = bounds
        clamped_x = max(bx, min(int(x), bx + bw - 1))
        clamped_y = max(by, min(int(y), by + bh - 1))
        return clamped_x, clamped_y

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
        local_x, local_y = self._clamp_mouse_coordinates(int(x), int(y))
        global_x = self.screen_origin_x + local_x
        global_y = self.screen_origin_y + local_y
        self.mouse.position = (global_x, global_y)
        self._update_committed_cursor_position(local_x, local_y, global_x, global_y)
        self._record_action_event(
            "cursor_move",
            x=local_x,
            y=local_y,
            global_x=global_x,
            global_y=global_y,
        )

    def _move_cursor_if_current(self, x: int, y: int, generation: int):
        if int(generation) != self._current_move_generation():
            return
        self._set_mouse_position(x, y)

    def _left_click_impl(self, x=None, y=None):
        if x is not None and y is not None:
            self._set_mouse_position(x, y)
        self.mouse.press(Button.left)
        time.sleep(0.008)
        self.mouse.release(Button.left)
        position = self._current_cursor_snapshot()
        self._record_action_event(
            "left_click",
            global_x=int(position["global_x"]),
            global_y=int(position["global_y"]),
        )

    def _double_click_impl(self, x=None, y=None):
        if x is not None and y is not None:
            self._set_mouse_position(x, y)
        self.mouse.press(Button.left)
        time.sleep(0.008)
        self.mouse.release(Button.left)
        time.sleep(0.050)
        self.mouse.press(Button.left)
        time.sleep(0.008)
        self.mouse.release(Button.left)
        position = self._current_cursor_snapshot()
        self._record_action_event(
            "double_click",
            global_x=int(position["global_x"]),
            global_y=int(position["global_y"]),
        )

    def _right_click_impl(self, x=None, y=None):
        if x is not None and y is not None:
            self._set_mouse_position(x, y)
        self.mouse.press(Button.right)
        time.sleep(0.008)
        self.mouse.release(Button.right)
        position = self._current_cursor_snapshot()
        self._record_action_event(
            "right_click",
            global_x=int(position["global_x"]),
            global_y=int(position["global_y"]),
        )

    def _scroll_impl(self, delta_x, delta_y):
        position = self._current_cursor_snapshot()
        self.mouse.position = (int(position["global_x"]), int(position["global_y"]))
        self.mouse.scroll(int(delta_x), int(delta_y))
        self._record_action_event(
            "scroll",
            delta_x=int(delta_x),
            delta_y=int(delta_y),
            global_x=int(position["global_x"]),
            global_y=int(position["global_y"]),
        )

    def move_cursor(self, x: int, y: int):
        """
        Public method to move the cursor.
        Called directly by gesture recognizers.
        """
        origin_ns = self._capture_latency_origin_for_action()
        generation = self._current_move_generation()
        # Movement can be high-frequency; dropping stale updates avoids queue backpressure.
        self._enqueue_action(
            self._move_cursor_if_current,
            (int(x), int(y), generation),
            origin_ns=origin_ns,
            drop_if_full=True,
        )

    def left_click(self, x: int = None, y: int = None):
        """
        Public method to perform left click.
        Called directly by gesture recognizers.
        """
        self._invalidate_pending_move_actions()
        origin_ns = self._capture_latency_origin_for_action()
        self._enqueue_action(self._left_click_impl, (x, y), origin_ns=origin_ns)

    def double_click(self, x: int = None, y: int = None):
        """
        Public method to perform double click.
        Called directly by gesture recognizers.
        """
        self._invalidate_pending_move_actions()
        origin_ns = self._capture_latency_origin_for_action()
        self._enqueue_action(self._double_click_impl, (x, y), origin_ns=origin_ns)

    def right_click(self, x: int = None, y: int = None):
        """
        Public method to perform right click.
        Called directly by gesture recognizers.
        """
        self._invalidate_pending_move_actions()
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
        self._invalidate_pending_move_actions()
        origin_ns = self._capture_latency_origin_for_action()
        self._enqueue_action(self._scroll_impl, (dx, dy), origin_ns=origin_ns)

    def hold_left_click(self):
        self._invalidate_pending_move_actions()
        self._enqueue_action(self.mouse.press, (Button.left,))
        self._record_action_event("left_button_down")

    def release_left_click(self):
        self._invalidate_pending_move_actions()
        self._enqueue_action(self.mouse.release, (Button.left,))
        self._record_action_event("left_button_up")

    def hold_right_click(self):
        self._invalidate_pending_move_actions()
        self._enqueue_action(self.mouse.press, (Button.right,))
        self._record_action_event("right_button_down")

    def release_right_click(self):
        self._invalidate_pending_move_actions()
        self._enqueue_action(self.mouse.release, (Button.right,))
        self._record_action_event("right_button_up")

    def _key_down(self, key_code: str):
        return self._keyboard_backend.key_down(key_code)

    def _key_up(self, key_code: str):
        return self._keyboard_backend.key_up(key_code)

    def press_key(self, key):
        self.key_down(key)

    def release_key(self, key):
        self.key_up(key)

    def press_and_release_key(self, key):
        self.tap_key(key)

    def perform_macro(self, keys: list):
        self.tap_hotkey(keys)

    def execute_macro_steps(self, steps):
        """Queue an ordered macro step chain for execution."""
        normalized_steps = []
        for step in steps or []:
            if isinstance(step, MacroActionStep):
                normalized_steps.append(step)
            else:
                normalized_steps.append(MacroActionStep.from_dict(step))
        if not normalized_steps:
            return

        origin_ns = self._capture_latency_origin_for_action()
        self._enqueue_action(self._execute_macro_steps_impl, (normalized_steps,), origin_ns=origin_ns)

    def _execute_macro_steps_impl(self, steps):
        for step in steps:
            step_type = step.step_type
            params = step.params

            if step_type == "tap_key":
                self._tap_key_impl(params["key"])
            elif step_type == "key_down":
                self._key_down(params["key"])
            elif step_type == "key_up":
                self._key_up(params["key"])
            elif step_type == "tap_hotkey":
                self._tap_hotkey_impl(params["keys"])
            elif step_type == "left_click":
                self._left_click_impl()
            elif step_type == "right_click":
                self._right_click_impl()
            elif step_type == "left_button_down":
                self.mouse.press(Button.left)
            elif step_type == "left_button_up":
                self.mouse.release(Button.left)
            elif step_type == "right_button_down":
                self.mouse.press(Button.right)
            elif step_type == "right_button_up":
                self.mouse.release(Button.right)
            elif step_type == "scroll":
                self._scroll_impl(params.get("delta_x", 0), params.get("delta_y", 0))
            elif step_type == "delay_ms":
                time.sleep(max(0, int(params.get("duration_ms", 0))) / 1000.0)

    def key_down(self, key_code: str):
        """Press and hold a keyboard key."""
        logical = normalize_key(key_code)
        if not logical:
            return

        try:
            if self._key_down(logical):
                self._record_action_event("key_down", key=logical)
        except Exception as e:
            print(f"Error on key_down('{logical}'): {e}")

    def key_up(self, key_code: str):
        """Release a keyboard key."""
        logical = normalize_key(key_code)
        if not logical:
            return

        try:
            if self._key_up(logical):
                self._record_action_event("key_up", key=logical)
        except Exception as e:
            print(f"Error on key_up('{logical}'): {e}")

    def tap_key(self, key_code: str):
        """Press and release a key."""
        logical = normalize_key(key_code)
        if not logical:
            return

        origin_ns = self._capture_latency_origin_for_action()
        self._enqueue_action(self._tap_key_impl, (logical,), origin_ns=origin_ns)

    def replace_recent_text(self, old_text: str, new_text: str = ""):
        """Backspace recently emitted text, then optionally type replacement text."""
        old_payload = str(old_text or "")
        new_payload = str(new_text or "")
        if not old_payload and not new_payload:
            return

        origin_ns = self._capture_latency_origin_for_action()
        self._enqueue_action(
            self._replace_recent_text_impl,
            (old_payload, new_payload),
            origin_ns=origin_ns,
        )

    def _tap_hotkey_impl(self, logical_keys):
        if self._keyboard_backend.tap_hotkey(logical_keys):
            self._record_action_event("tap_hotkey", keys=list(logical_keys))

    def tap_hotkey(self, key_codes):
        """Press keys together as one hotkey chord, then release."""
        if not isinstance(key_codes, (list, tuple)):
            return
        logical_keys = []
        for key in key_codes:
            logical = normalize_key(key)
            if logical:
                logical_keys.append(logical)
        if not logical_keys:
            return

        origin_ns = self._capture_latency_origin_for_action()
        self._enqueue_action(self._tap_hotkey_impl, (logical_keys,), origin_ns=origin_ns)

    def _tap_key_impl(self, logical):
        if self._keyboard_backend.tap_key(logical):
            self._record_action_event("tap_key", key=logical)

    def _replace_recent_text_impl(self, old_payload: str, new_payload: str):
        self.release_all_keys()

        if old_payload:
            for _ in range(len(old_payload)):
                self._tap_key_impl("backspace")

        if old_payload and new_payload:
            time.sleep(0.005)

        if new_payload:
            self._type_text_impl(new_payload)

    def type_text(self, text):
        """Type a text string in one action."""
        if text is None:
            return
        payload = str(text)
        if not payload:
            return
        origin_ns = self._capture_latency_origin_for_action()
        self._enqueue_action(self._type_text_impl, (payload,), origin_ns=origin_ns)

    def _type_text_impl(self, payload: str):
        scope = self._current_tutorial_scope()
        if scope.get("capture_text"):
            self._record_action_event("type_text", text=payload, captured=True)
            return
        self.release_all_keys()
        if self._keyboard_backend.type_text(payload):
            self._record_action_event("type_text", text=payload, captured=False)

    def release_all_keys(self):
        """Release any currently held keys."""
        try:
            self._keyboard_backend.release_all_keys()
        except Exception as e:
            print(f"Error releasing held keys: {e}")

    def close(self):
        """Stop background action worker."""
        if self._worker_stop.is_set():
            return
        self.release_all_keys()

        if getattr(self, "_keyboard_backend", None):
            try:
                self._keyboard_backend.shutdown()
            except Exception as e:
                print(f"Error shutting down keyboard backend: {e}")
            self._keyboard_backend = None
            self._windows_backend = None
            self._send_input = None

        self._worker_stop.set()
        try:
            self._action_queue.put_nowait((None, (), None))
        except queue.Full:
            pass
        if self._worker.is_alive():
            self._worker.join(timeout=0.25)
