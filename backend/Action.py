import os
import platform
import queue
import shutil
import subprocess
import threading
import time
from collections import deque
from copy import deepcopy

from backend.macros.macro_models import MacroActionStep
from backend.gestures.keyboard_mode.KeyCodes import normalize_key
from pynput.mouse import Controller as Mouse, Button
from pynput.keyboard import Controller as Keyboard, Key
from pyparsing import ABC, abstractmethod

OS_TYPE = platform.system()
if OS_TYPE == "Windows":
    from backend.platforms.WindowsKeyboardBackend import WindowsKeyboardBackend


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
        self.mouse = mouse if mouse is not None else Mouse()
        self.keyboard = keyboard_test if keyboard_test is not None else Keyboard()
        self.osType = osType if osType is not None else OS_TYPE
        self.screen_origin_x = int(screen_origin_x)
        self.screen_origin_y = int(screen_origin_y)
        self.detected_os = self.osType
        self._held_keys = set()
        self._keyboard_send_failures = 0
        self._keyboard_disabled = False
        self._xdotool_path = shutil.which("xdotool") if self.detected_os == "Linux" else None
        self._ydotool_path = shutil.which("ydotool") if self.detected_os == "Linux" else None
        self._linux_session_type = (
            os.environ.get("XDG_SESSION_TYPE", "").strip().lower() if self.detected_os == "Linux" else ""
        )
        self._warned_missing_xdotool = False
        self._warned_missing_ydotool = False

        # Windows-specific backend
        if self.detected_os == "Windows":
            self._windows_backend = WindowsKeyboardBackend()
            self._windows_backend.initialize()

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

    def _pynput_meta_key(self, side: str):
        """Resolve platform-appropriate meta/super/cmd key for the given side."""
        is_left = side == "left"
        side_super = "super_l" if is_left else "super_r"
        side_cmd = "cmd_l" if is_left else "cmd_r"

        if self.detected_os == "Linux":
            return (
                getattr(Key, side_super, None)
                or getattr(Key, side_cmd, None)
                or getattr(Key, "cmd", None)
            )
        if self.detected_os == "Darwin":
            return getattr(Key, side_cmd, None) or getattr(Key, "cmd", None)
        return getattr(Key, side_cmd, None) or getattr(Key, "cmd", None)

    def _pynput_key_from_logical(self, key_code: str):
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

    def _key_down_via_pynput(self, key_code: str):
        key = self._pynput_key_from_logical(key_code)
        if key is None:
            print(f"Warning: unsupported key code '{key_code}'")
            return False
        return self._enqueue_action(self.keyboard.press, (key,))

    def _key_up_via_pynput(self, key_code: str):
        key = self._pynput_key_from_logical(key_code)
        if key is None:
            return False
        return self._enqueue_action(self.keyboard.release, (key,))

    def _key_down(self, key_code: str):
        if self.detected_os == "Windows":
            if self._windows_backend:
                return self._windows_backend.key_down(key_code)
            return self._key_down_via_pynput(key_code)
        return self._key_down_via_pynput(key_code)

    def _key_up(self, key_code: str):
        if self.detected_os == "Windows":
            if self._windows_backend:
                return self._windows_backend.key_up(key_code)
            return self._key_up_via_pynput(key_code)
        return self._key_up_via_pynput(key_code)

    def press_key(self, key):
        self._enqueue_action(self.keyboard.press, (key,))

    def release_key(self, key):
        self._enqueue_action(self.keyboard.release, (key,))

    def press_and_release_key(self, key):
        self.press_key(key)
        self.release_key(key)

    def perform_macro(self, keys: list):
        for key in keys:
            self.press_key(key)
            
        for key in keys:
            self.release_key(key)

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
                if self._key_down(params["key"]):
                    self._held_keys.add(params["key"])
            elif step_type == "key_up":
                self._key_up(params["key"])
                self._held_keys.discard(params["key"])
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
        if not logical or logical in self._held_keys:
            return

        try:
            if self._key_down(logical):
                self._held_keys.add(logical)
                self._record_action_event("key_down", key=logical)
        except Exception as e:
            print(f"Error on key_down('{logical}'): {e}")

    def key_up(self, key_code: str):
        """Release a keyboard key."""
        logical = normalize_key(key_code)
        if not logical:
            return

        try:
            self._key_up(logical)
            self._record_action_event("key_up", key=logical)
        except Exception as e:
            print(f"Error on key_up('{logical}'): {e}")
        finally:
            self._held_keys.discard(logical)

    def tap_key(self, key_code: str):
        """Press and release a key."""
        logical = normalize_key(key_code)
        if not logical:
            return

        origin_ns = self._capture_latency_origin_for_action()
        self._enqueue_action(self._tap_key_impl, (logical,), origin_ns=origin_ns)

    def _tap_hotkey_impl_pynput(self, logical_keys):
        resolved_keys = []
        for logical in logical_keys:
            key = self._pynput_key_from_logical(logical)
            if key is None:
                print(f"Warning: unsupported key code in hotkey '{logical}'")
                return
            resolved_keys.append(key)

        try:
            for key in resolved_keys:
                self.keyboard.press(key)
            # Small delay improves OS detection for composed shortcuts.
            time.sleep(0.010)
        finally:
            for key in reversed(resolved_keys):
                try:
                    self.keyboard.release(key)
                except Exception:
                    pass

    def _tap_hotkey_impl_linux(self, logical_keys):
        for backend in self._linux_keyboard_backend_order():
            if backend == "xdotool":
                if self._tap_hotkey_impl_xdotool(logical_keys):
                    return
            elif backend == "ydotool":
                if self._tap_hotkey_impl_ydotool(logical_keys):
                    return
            else:
                self._tap_hotkey_impl_pynput(logical_keys)
                return

    def _tap_hotkey_impl(self, logical_keys):
        if self.detected_os == "Linux":
            self._tap_hotkey_impl_linux(logical_keys)
        else:
            self._tap_hotkey_impl_pynput(logical_keys)
        self._record_action_event("tap_hotkey", keys=list(logical_keys))

    def _logical_to_xdotool_key(self, logical: str):
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
            "f1": "F1",
            "f2": "F2",
            "f3": "F3",
            "f4": "F4",
            "f5": "F5",
            "f6": "F6",
            "f7": "F7",
            "f8": "F8",
            "f9": "F9",
            "f10": "F10",
            "f11": "F11",
            "f12": "F12",
        }
        return key_lookup.get(logical)

    def _logical_to_ydotool_code(self, logical: str):
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
            "f1": 59,
            "f2": 60,
            "f3": 61,
            "f4": 62,
            "f5": 63,
            "f6": 64,
            "f7": 65,
            "f8": 66,
            "f9": 67,
            "f10": 68,
            "f11": 87,
            "f12": 88,
        }
        return key_lookup.get(logical)

    def _linux_keyboard_backend_order(self):
        if self.detected_os != "Linux":
            return []

        preferred = ["ydotool", "xdotool", "pynput"] if self._linux_session_type == "wayland" else ["xdotool", "ydotool", "pynput"]
        available = []
        for backend in preferred:
            if backend == "xdotool" and self._xdotool_path:
                available.append("xdotool")
            elif backend == "ydotool" and self._ydotool_path:
                available.append("ydotool")
            elif backend == "pynput":
                available.append("pynput")
        return available

    def _run_input_command(self, args):
        try:
            result = subprocess.run(
                args,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _tap_key_impl_xdotool(self, logical: str):
        if not self._xdotool_path:
            return False
        key = self._logical_to_xdotool_key(logical)
        if not key:
            return False
        return self._run_input_command([self._xdotool_path, "key", "--", key])

    def _tap_key_impl_ydotool(self, logical: str):
        if not self._ydotool_path:
            return False
        code = self._logical_to_ydotool_code(logical)
        if code is None:
            return False
        return self._run_input_command([self._ydotool_path, "key", f"{code}:1", f"{code}:0"])

    def _tap_key_impl_pynput(self, logical: str):
        key = self._pynput_key_from_logical(logical)
        if key is None:
            return False
        try:
            self.keyboard.press(key)
            time.sleep(0.005)
            self.keyboard.release(key)
            return True
        except Exception:
            return False

    def _tap_key_impl_linux(self, logical: str):
        for backend in self._linux_keyboard_backend_order():
            if backend == "xdotool" and self._tap_key_impl_xdotool(logical):
                return True
            if backend == "ydotool" and self._tap_key_impl_ydotool(logical):
                return True
            if backend == "pynput" and self._tap_key_impl_pynput(logical):
                return True
        return False

    def _type_text_impl_xdotool(self, text: str):
        if not self._xdotool_path:
            return False
        return self._run_input_command([self._xdotool_path, "type", "--clearmodifiers", "--delay", "0", "--", text])

    def _type_text_impl_ydotool(self, text: str):
        if not self._ydotool_path:
            return False
        return self._run_input_command([self._ydotool_path, "type", text])

    def _type_text_impl_pynput(self, text: str):
        try:
            self.keyboard.type(text)
            return True
        except Exception:
            return False

    def _type_text_impl_linux(self, text: str):
        for backend in self._linux_keyboard_backend_order():
            if backend == "xdotool" and self._type_text_impl_xdotool(text):
                return True
            if backend == "ydotool" and self._type_text_impl_ydotool(text):
                return True
            if backend == "pynput" and self._type_text_impl_pynput(text):
                return True
        return False

    def _tap_hotkey_impl_xdotool(self, logical_keys):
        if not self._xdotool_path:
            return False

        keys = []
        for logical in logical_keys:
            key = self._logical_to_xdotool_key(logical)
            if not key:
                return False
            keys.append(key)

        chord = "+".join(keys)
        return self._run_input_command([self._xdotool_path, "key", "--", chord])

    def _tap_hotkey_impl_ydotool(self, logical_keys):
        if not self._ydotool_path:
            return False

        codes = []
        for logical in logical_keys:
            code = self._logical_to_ydotool_code(logical)
            if code is None:
                return False
            codes.append(code)
        if not codes:
            return False

        events = []
        for code in codes[:-1]:
            events.append(f"{code}:1")
        events.append(f"{codes[-1]}:1")
        events.append(f"{codes[-1]}:0")
        for code in reversed(codes[:-1]):
            events.append(f"{code}:0")
        return self._run_input_command([self._ydotool_path, "key", *events])

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
        if self.detected_os == "Linux":
            if self._tap_key_impl_linux(logical):
                self._record_action_event("tap_key", key=logical)
                return
            print(f"Warning: failed to inject Linux key tap '{logical}' via xdotool/ydotool/pynput")
            return
        self._tap_key_impl_pynput(logical)
        self._record_action_event("tap_key", key=logical)

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
        if self.detected_os == "Linux":
            if self._type_text_impl_linux(payload):
                self._record_action_event("type_text", text=payload, captured=False)
                return
            print("Warning: failed to inject Linux text via xdotool/ydotool/pynput")
            return
        self._type_text_impl_pynput(payload)
        self._record_action_event("type_text", text=payload, captured=False)

    def release_all_keys(self):
        """Release any currently held keys."""
        for key in list(self._held_keys):
            try:
                self._key_up(key)
            except Exception as e:
                print(f"Error releasing key '{key}': {e}")
        self._held_keys.clear()

    def close(self):
        """Stop background action worker."""
        if self._worker_stop.is_set():
            return
        self.release_all_keys()
        self._worker_stop.set()
        try:
            self._action_queue.put_nowait((None, (), None))
        except queue.Full:
            pass
        if self._worker.is_alive():
            self._worker.join(timeout=0.25)
