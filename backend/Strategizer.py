from enum import Enum
import time

from backend.HandsData import HandsData
from backend.macros.macro_store import MacroStore
from backend.gesture_remap.builtins import BuiltInGestureRegistry
from backend.gesture_remap.override_store import GestureOverrideStore
from backend.gestures.GestureUtils import are_fingers_pinched, is_finger_extended


class ControlMode(Enum):
    IDLE = "idle"
    MOUSE = "mouse"
    KEYBOARD = "keyboard"
    HOTKEY = "hotkey"


class Strategizer:

    def __init__(
        self,
        action,
        config,
        screen_width,
        screen_height,
        ui_mode="dev",
    ):
        """
        Initialize the Strategizer.

        Args:
            action: Action object for executing system commands
            config: GestureConfig object with settings
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
        """
        self.action = action
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.config = config
        self.ui_mode = str(ui_mode)
        if hasattr(self.action, "configure_cursor_move_smoothing"):
            try:
                self.action.configure_cursor_move_smoothing(
                    self.config.get("cursor_move_smoothing", 0.0)
                )
            except Exception:
                pass

        # Default mode is mouse mode (Can be changed for easier manual testing)
        self.current_mode = ControlMode.MOUSE

        # Gesture recognizers for each mode
        self.switch_mode_gestures = []
        self.mouse_mode_gestures = []
        self.keyboard_mode_gestures = []
        self.hotkey_mode_gestures = []
        self._sorted_mouse_mode_gestures = []
        self._sorted_keyboard_mode_gestures = []
        self._sorted_hotkey_mode_gestures = []
        self._custom_gesture_instances = []
        self._last_mode_switch_ts = 0.0
        self.gesture_override_store = GestureOverrideStore.from_config(config)
        self.macro_store = MacroStore.from_config(
            config,
            target_os=getattr(self.action, "detected_os", None),
        )
        self._debug_snapshot = self._empty_debug_snapshot()

        # Initialize built-in mode-specific gestures before loading JSON rules.
        self._initialize_mouse_mode()
        self._initialize_keyboard_mode()
        self._initialize_switch_mode()
        self._reload_customizations()

    def _initialize_mouse_mode(self):
        """Initialize gesture recognizers for mouse mode."""
        self.mouse_mode_gestures = [
            BuiltInGestureRegistry.build_runtime_gesture("left_click", self, self.gesture_override_store),
            BuiltInGestureRegistry.build_runtime_gesture("right_click", self, self.gesture_override_store),
            BuiltInGestureRegistry.build_runtime_gesture("scroll", self, self.gesture_override_store),
            BuiltInGestureRegistry.build_runtime_gesture("mouse_move", self, self.gesture_override_store),
        ]
        self._rebuild_sorted_gestures(ControlMode.MOUSE)

    def _initialize_switch_mode(self):
        """Initialize gesture recognizers for switching from one mode to another."""
        self.switch_mode_gestures = [
            BuiltInGestureRegistry.build_runtime_gesture("switch_to_keyboard", self, self.gesture_override_store),
            BuiltInGestureRegistry.build_runtime_gesture("switch_to_hotkey", self, self.gesture_override_store),
            BuiltInGestureRegistry.build_runtime_gesture("switch_to_mouse", self, self.gesture_override_store),
        ]

    def _initialize_keyboard_mode(self):
        """Initialize gesture recognizers for keyboard mode."""
        from backend.gestures.keyboard_mode.AirTypingGesture import AirTypingGesture

        self.keyboard_mode_gestures = [
            AirTypingGesture(
                self.action,
                config=self.config,
                priority=15,
                ui_mode=self.ui_mode,
                screen_width=self.screen_width,
                screen_height=self.screen_height,
            )
        ]
        self.keyboard_mode_gestures[0].debug_name = "Air Typing"
        self._rebuild_sorted_gestures(ControlMode.KEYBOARD)

    def set_mode(self, mode: ControlMode):
        """
        Change the current control mode.

        Args:
            mode: ControlMode to switch to
        """
        if mode != self.current_mode:
            self._reset_current_mode_gestures()

            if hasattr(self.action, "release_all_keys"):
                self.action.release_all_keys()

            self.current_mode = mode
            self._last_mode_switch_ts = time.time()
            self._reset_mode_gestures(mode)
            if hasattr(self.action, "show_feedback_message"):
                try:
                    self.action.show_feedback_message(mode.value.title(), feedback_type="mode")
                except Exception:
                    pass
            print(f"Switched to {mode.value} mode")

    def _reset_current_mode_gestures(self):
        """Reset all gesture recognizers in the current mode."""
        for gesture in self._get_current_mode_gestures():
            gesture.reset()

    def _reset_mode_gestures(self, mode: ControlMode):
        """Reset all gesture recognizers for a specific mode."""
        if mode == ControlMode.MOUSE:
            gestures = self.mouse_mode_gestures
        elif mode == ControlMode.KEYBOARD:
            gestures = self.keyboard_mode_gestures
        elif mode == ControlMode.HOTKEY:
            gestures = self.hotkey_mode_gestures
        else:
            gestures = []

        for gesture in gestures:
            gesture.reset()

    def _get_current_mode_gestures(self):
        """Get gesture recognizers for the current mode."""
        if self.current_mode == ControlMode.MOUSE:
            return self.mouse_mode_gestures
        if self.current_mode == ControlMode.KEYBOARD:
            return self.keyboard_mode_gestures
        if self.current_mode == ControlMode.HOTKEY:
            return self.hotkey_mode_gestures
        return []

    def _get_current_mode_sorted_gestures(self):
        """Get pre-sorted gesture recognizers for the current mode."""
        if self.current_mode == ControlMode.MOUSE:
            return self._sorted_mouse_mode_gestures
        if self.current_mode == ControlMode.KEYBOARD:
            return self._sorted_keyboard_mode_gestures
        if self.current_mode == ControlMode.HOTKEY:
            return self._sorted_hotkey_mode_gestures
        return []

    def _rebuild_sorted_gestures(self, mode: ControlMode):
        """Rebuild the cached priority-sorted gesture list for a mode."""
        if mode == ControlMode.MOUSE:
            self._sorted_mouse_mode_gestures = sorted(
                self.mouse_mode_gestures, key=lambda g: g.priority, reverse=True
            )
        elif mode == ControlMode.KEYBOARD:
            self._sorted_keyboard_mode_gestures = sorted(
                self.keyboard_mode_gestures, key=lambda g: g.priority, reverse=True
            )
        elif mode == ControlMode.HOTKEY:
            self._sorted_hotkey_mode_gestures = sorted(
                self.hotkey_mode_gestures, key=lambda g: g.priority, reverse=True
            )

    def strategize(self, hands_data: HandsData, frame_capture_ts_ns=None):
        """
        Update all gesture recognizers for the current mode.

        Uses priority-based conflict resolution:
        - Higher priority gestures are checked first
        - Once a high-priority gesture is active, lower-priority gestures are skipped

        Args:
            hands_data: Current hand landmark data
            frame_capture_ts_ns: Frame capture timestamp (ns) for latency tracking
        """
        mode_switch_cooldown = self.config.get("keyboard_mode_switch_cooldown_sec", 1.0)
        elapsed_since_switch = time.time() - self._last_mode_switch_ts

        if elapsed_since_switch >= mode_switch_cooldown:
            sorted_switch_gestures = sorted(
                self.switch_mode_gestures, key=lambda g: g.priority, reverse=True
            )
            switch_entries = []
            keyboard_exit_block_note = self._keyboard_mode_exit_block_note()
            for switch_gesture in sorted_switch_gestures:
                if (
                    keyboard_exit_block_note
                    and getattr(switch_gesture, "debug_gesture_id", "") == "switch_to_mouse"
                ):
                    switch_entries.append(
                        self._gesture_debug_entry(
                            switch_gesture,
                            suppressed=True,
                            note=keyboard_exit_block_note,
                            evaluated=False,
                        )
                    )
                    continue
                action_executed = switch_gesture.update(hands_data)
                switch_entries.append(self._gesture_debug_entry(switch_gesture))
                if action_executed:
                    self._debug_snapshot = self._build_debug_snapshot(
                        hands_data,
                        mode_switch_entries=switch_entries,
                        mode_entries=self._suppressed_entries(
                            self._get_current_mode_sorted_gestures(),
                            "Mode switch took priority",
                        ),
                        winning_action=self._winning_action_from_gesture(switch_gesture),
                    )
                    return
        else:
            switch_entries = self._cooldown_entries(self.switch_mode_gestures, "Mode switch cooldown")

        sorted_gestures = self._get_current_mode_sorted_gestures()
        high_priority_active = False
        active_priority = None
        mode_entries = []
        winning_action = None

        for gesture in sorted_gestures:
            if (
                high_priority_active
                and active_priority is not None
                and gesture.priority < active_priority
            ):
                mode_entries.append(
                    self._gesture_debug_entry(
                        gesture,
                        suppressed=True,
                        note="Suppressed by higher priority gesture",
                        evaluated=False,
                    )
                )
                continue

            action_executed = gesture.update(
                hands_data, frame_capture_ts_ns=frame_capture_ts_ns
            )
            mode_entries.append(self._gesture_debug_entry(gesture))

            if (
                (
                    getattr(gesture, "consumes_events", False)
                    or getattr(gesture, "suppresses_lower_priorities_while_active", False)
                )
                and gesture.is_active
            ):
                high_priority_active = True
                if active_priority is None:
                    active_priority = gesture.priority
                else:
                    active_priority = max(active_priority, gesture.priority)

            if action_executed and gesture.priority >= 5:
                high_priority_active = True
                if active_priority is None:
                    active_priority = gesture.priority
                else:
                    active_priority = max(active_priority, gesture.priority)
            if action_executed and winning_action is None:
                winning_action = self._winning_action_from_gesture(gesture)

        self._debug_snapshot = self._build_debug_snapshot(
            hands_data,
            mode_switch_entries=switch_entries,
            mode_entries=mode_entries,
            winning_action=winning_action,
        )

    def _keyboard_mode_exit_block_note(self) -> str:
        if self.current_mode != ControlMode.KEYBOARD:
            return ""
        for gesture in self.keyboard_mode_gestures:
            block_method = getattr(gesture, "blocks_keyboard_mode_exit", None)
            if not callable(block_method):
                continue
            note = str(block_method() or "").strip()
            if note:
                return note
        return ""

    def get_mode_name(self):
        return self.current_mode.value.upper()

    def _empty_debug_snapshot(self):
        return {
            "mode": self.get_mode_name(),
            "hands": [],
            "mode_switch_candidates": [],
            "mode_candidates": [],
            "winning_action": None,
            "action_debug": None,
        }

    def _gesture_display_name(self, gesture):
        return (
            getattr(gesture, "debug_name", None)
            or getattr(gesture, "name", None)
            or getattr(gesture, "debug_gesture_id", None)
            or gesture.__class__.__name__
        )

    def _gesture_state_value(self, gesture):
        state = getattr(gesture, "current_state", None)
        return getattr(state, "value", str(state)).lower() if state is not None else "unknown"

    def _gesture_debug_entry(self, gesture, *, suppressed=False, note=None, evaluated=True):
        entry_note = note if note is not None else getattr(gesture, "_debug_last_note", "")
        state = self._gesture_state_value(gesture)
        if suppressed:
            state = "suppressed"
        return {
            "name": self._gesture_display_name(gesture),
            "priority": int(getattr(gesture, "priority", 0)),
            "state": state,
            "detected": bool(getattr(gesture, "_debug_last_detected", False)) if evaluated else False,
            "active": bool(getattr(gesture, "is_active", False)),
            "executed": bool(getattr(gesture, "_debug_last_action_executed", False)) if evaluated else False,
            "suppressed": bool(suppressed),
            "note": str(entry_note or ""),
        }

    def _suppressed_entries(self, gestures, note):
        return [
            self._gesture_debug_entry(
                gesture,
                suppressed=True,
                note=note,
                evaluated=False,
            )
            for gesture in gestures
        ]

    def _cooldown_entries(self, gestures, note):
        entries = []
        for gesture in sorted(gestures, key=lambda g: g.priority, reverse=True):
            entries.append(
                {
                    "name": self._gesture_display_name(gesture),
                    "priority": int(getattr(gesture, "priority", 0)),
                    "state": "cooldown",
                    "detected": False,
                    "active": bool(getattr(gesture, "is_active", False)),
                    "executed": False,
                    "suppressed": False,
                    "note": note,
                }
            )
        return entries

    def _winning_action_from_gesture(self, gesture):
        return {
            "name": self._gesture_display_name(gesture),
            "priority": int(getattr(gesture, "priority", 0)),
            "note": str(getattr(gesture, "_debug_last_note", "") or ""),
        }

    def _hand_debug_entry(self, side, wrist_hand, camera_hand):
        finger_names = ("thumb", "index", "middle", "ring", "pinky")
        present = wrist_hand.exists and camera_hand.exists
        if not present:
            return {
                "side": side,
                "present": False,
                "extended": {},
                "extended_fingers": [],
                "curled_fingers": [],
                "pinches": {},
                "detected_pinches": [],
            }

        extension_threshold = float(self.config["finger_extension_angle"])
        pinch_threshold = float(self.config["pinch_threshold"])
        extended = {
            finger_name: bool(is_finger_extended(getattr(wrist_hand, finger_name), threshold=extension_threshold))
            for finger_name in finger_names
        }
        detected_pinches = []
        pinches = {}
        pinch_pairs = (
            ("thumb_index", "thumb", "index"),
            ("thumb_middle", "thumb", "middle"),
            ("thumb_ring", "thumb", "ring"),
            ("thumb_pinky", "thumb", "pinky"),
        )
        for key, finger_a, finger_b in pinch_pairs:
            is_pinched = bool(
                are_fingers_pinched(
                    getattr(wrist_hand, finger_a).tip,
                    getattr(wrist_hand, finger_b).tip,
                    pinch_threshold,
                )
            )
            pinches[key] = is_pinched
            if is_pinched:
                detected_pinches.append(f"{finger_a.title()} + {finger_b.title()}")

        extended_fingers = [finger_name.title() for finger_name in finger_names if extended[finger_name]]
        curled_fingers = [finger_name.title() for finger_name in finger_names if not extended[finger_name]]
        return {
            "side": side,
            "present": True,
            "extended": extended,
            "extended_fingers": extended_fingers,
            "curled_fingers": curled_fingers,
            "pinches": pinches,
            "detected_pinches": detected_pinches,
        }

    def _build_debug_snapshot(self, hands_data: HandsData, *, mode_switch_entries, mode_entries, winning_action):
        action_debug = None
        if hasattr(self.action, "get_runtime_debug_snapshot"):
            action_debug = self.action.get_runtime_debug_snapshot()
        return {
            "mode": self.get_mode_name(),
            "hands": [
                self._hand_debug_entry("Left", hands_data.wrist.left, hands_data.camera.left),
                self._hand_debug_entry("Right", hands_data.wrist.right, hands_data.camera.right),
            ],
            "mode_switch_candidates": mode_switch_entries,
            "mode_candidates": mode_entries,
            "winning_action": winning_action,
            "action_debug": action_debug,
        }

    def capture_debug_snapshot(self, hands_data: HandsData):
        self._debug_snapshot = self._build_debug_snapshot(
            hands_data,
            mode_switch_entries=self._cooldown_entries(self.switch_mode_gestures, "Not evaluated this frame"),
            mode_entries=[
                self._gesture_debug_entry(gesture, evaluated=False)
                for gesture in self._get_current_mode_sorted_gestures()
            ],
            winning_action=None,
        )

    def get_debug_snapshot(self):
        return self._debug_snapshot

    def get_keyboard_overlay_data(self):
        """Get overlay/debug data from keyboard typing recognizer when available."""
        if self.current_mode != ControlMode.KEYBOARD:
            return None

        for gesture in self.keyboard_mode_gestures:
            if hasattr(gesture, "get_overlay_data"):
                return gesture.get_overlay_data()
        return None

    def add_custom_gesture(self, gesture, mode: ControlMode = None):
        """
        Add a custom gesture recognizer to a specific mode.

        Args:
            gesture: GestureRecognizer instance
            mode: ControlMode to add to (defaults to current mode)
        """
        if mode is None:
            mode = self.current_mode

        if mode == ControlMode.MOUSE:
            self.mouse_mode_gestures.append(gesture)
            self._rebuild_sorted_gestures(ControlMode.MOUSE)
        elif mode == ControlMode.KEYBOARD:
            self.keyboard_mode_gestures.append(gesture)
            self._rebuild_sorted_gestures(ControlMode.KEYBOARD)
        elif mode == ControlMode.HOTKEY:
            self.hotkey_mode_gestures.append(gesture)
            self._rebuild_sorted_gestures(ControlMode.HOTKEY)

    def get_active_gestures(self):
        """
        Get list of currently active gestures.

        Returns:
            list: Active gesture recognizers
        """
        return [g for g in self._get_current_mode_gestures() if g.is_active]

    def remove_gesture(self, gesture, mode: ControlMode = None):
        """
        Remove a gesture recognizer from a specific mode.

        Args:
            gesture: GestureRecognizer instance to remove
            mode: ControlMode to remove from (defaults to current mode)
        """
        if mode is None:
            mode = self.current_mode

        if mode == ControlMode.MOUSE and gesture in self.mouse_mode_gestures:
            self.mouse_mode_gestures.remove(gesture)
            self._rebuild_sorted_gestures(ControlMode.MOUSE)
        elif mode == ControlMode.KEYBOARD and gesture in self.keyboard_mode_gestures:
            self.keyboard_mode_gestures.remove(gesture)
            self._rebuild_sorted_gestures(ControlMode.KEYBOARD)
        elif mode == ControlMode.HOTKEY and gesture in self.hotkey_mode_gestures:
            self.hotkey_mode_gestures.remove(gesture)
            self._rebuild_sorted_gestures(ControlMode.HOTKEY)

    def _reload_customizations(self):
        from backend.custom_rules.RuleCompiler import RuleCompiler

        for gesture in getattr(self, "_custom_gesture_instances", []):
            if gesture in self.mouse_mode_gestures:
                self.mouse_mode_gestures.remove(gesture)
            if gesture in self.keyboard_mode_gestures:
                self.keyboard_mode_gestures.remove(gesture)
            if gesture in self.hotkey_mode_gestures:
                self.hotkey_mode_gestures.remove(gesture)

        self._custom_gesture_instances = []
        self._rebuild_sorted_gestures(ControlMode.MOUSE)
        self._rebuild_sorted_gestures(ControlMode.KEYBOARD)
        self._rebuild_sorted_gestures(ControlMode.HOTKEY)

        compiler = RuleCompiler(self.config, self.screen_width, self.screen_height)

        for macro_record in self.macro_store.list_records():
            if not macro_record.enabled:
                continue

            if macro_record.mode == "mouse":
                mode = ControlMode.MOUSE
            elif macro_record.mode == "keyboard":
                mode = ControlMode.KEYBOARD
            else:
                mode = ControlMode.HOTKEY

            try:
                recognizer = compiler.compile_ui_macro(self.action, macro_record)
                self.add_custom_gesture(recognizer, mode=mode)
                self._custom_gesture_instances.append(recognizer)
                print(f"[OK] Loaded UI macro: {macro_record.name} ({macro_record.mode})")
            except Exception as exc:
                print(f"[WARN] Skipped UI macro {macro_record.name}: {exc}")

    def shutdown(self):
        """Reset all gestures and release held state before process/UI shutdown."""
        for gesture_list in (
            self.mouse_mode_gestures,
            self.keyboard_mode_gestures,
            self.hotkey_mode_gestures,
        ):
            for gesture in gesture_list:
                try:
                    gesture.reset()
                except Exception:
                    pass

        if hasattr(self.action, "release_all_keys"):
            self.action.release_all_keys()
