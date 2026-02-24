import platform
import queue
import shutil
import subprocess
import threading
import time
from collections import deque

from backend.gestures.keyboard_mode.KeyCodes import get_windows_vk, normalize_key
from pynput.mouse import Controller as Mouse, Button
from pynput.keyboard import Controller as Keyboard, Key
from pyparsing import ABC, abstractmethod

OS_TYPE = platform.system()
if OS_TYPE == "Windows":
    import ctypes
    from ctypes import wintypes


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

    def __init__(self, mouse: MouseTest = None, keyboard_test: KeyboardTest = None, osType=None):
        self.mouse = mouse if mouse is not None else Mouse()
        self.keyboard = keyboard_test if keyboard_test is not None else Keyboard()
        self.osType = osType if osType is not None else OS_TYPE
        self.detected_os = self.osType
        self._held_keys = set()
        self._keyboard_send_failures = 0
        self._keyboard_disabled = False
        self._xdotool_path = shutil.which("xdotool") if self.detected_os == "Linux" else None
        self._warned_missing_xdotool = False

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

        if self.detected_os == "Windows":
            self._init_windows_keyboard_structs()

    def _init_windows_keyboard_structs(self):
        """Create ctypes structures for Windows SendInput keyboard injection."""
        self.INPUT_KEYBOARD = 1
        self.KEYEVENTF_KEYUP = 0x0002
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

        self._INPUTUNION = _INPUTUNION
        self._KEYBDINPUT = KEYBDINPUT
        self._INPUT = INPUT

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
            return self._key_down_via_pynput(key_code)
        return self._send_key_event_windows(vk_code, key_up=False)

    def _key_up_windows(self, key_code: str):
        vk_code = get_windows_vk(key_code)
        if vk_code is None:
            return self._key_up_via_pynput(key_code)
        return self._send_key_event_windows(vk_code, key_up=True)

    def _key_down(self, key_code: str):
        if self.detected_os == "Windows":
            return self._key_down_windows(key_code)
        return self._key_down_via_pynput(key_code)

    def _key_up(self, key_code: str):
        if self.detected_os == "Windows":
            return self._key_up_windows(key_code)
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

    def key_down(self, key_code: str):
        """Press and hold a keyboard key."""
        logical = normalize_key(key_code)
        if not logical or logical in self._held_keys:
            return

        try:
            if self._key_down(logical):
                self._held_keys.add(logical)
        except Exception as e:
            print(f"Error on key_down('{logical}'): {e}")

    def key_up(self, key_code: str):
        """Release a keyboard key."""
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
        """Press and release a key."""
        logical = normalize_key(key_code)
        if not logical:
            return

        self.key_down(logical)
        # Keep tap tight but explicit to maintain event ordering.
        time.sleep(0.005)
        self.key_up(logical)

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
        if any(k in {"left_win", "right_win"} for k in logical_keys):
            if self._tap_hotkey_impl_xdotool(logical_keys):
                return
            if not self._warned_missing_xdotool:
                print("Warning: xdotool unavailable or unsupported hotkey; falling back to pynput")
                self._warned_missing_xdotool = True
        self._tap_hotkey_impl_pynput(logical_keys)

    def _tap_hotkey_impl(self, logical_keys):
        if self.detected_os == "Linux":
            self._tap_hotkey_impl_linux(logical_keys)
            return
        self._tap_hotkey_impl_pynput(logical_keys)

    def _logical_to_xdotool_key(self, logical: str):
        if len(logical) == 1:
            return logical

        key_lookup = {
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
            "space": "space",
        }
        return key_lookup.get(logical)

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
        try:
            subprocess.run(
                [self._xdotool_path, "key", "--", chord],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

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

    def type_text(self, text):
        """Type a text string in one action."""
        if text is None:
            return
        payload = str(text)
        if not payload:
            return
        origin_ns = self._capture_latency_origin_for_action()
        self._enqueue_action(self.keyboard.type, (payload,), origin_ns=origin_ns)

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
