from enum import Enum
import time

from backend.HandsData import HandsData
from backend.macros.macro_store import MacroStore
from backend.gesture_remap.builtins import BuiltInGestureRegistry
from backend.gesture_remap.override_store import GestureOverrideStore


class ControlMode(Enum):
    IDLE = "idle"
    MOUSE = "mouse"
    KEYBOARD = "keyboard"
    HOTKEY = "hotkey"


class Strategizer:

    def __init__(self, action, config, screen_width, screen_height, ui_mode="dev"):
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
        self.macro_store = MacroStore.from_config(config)

        # Initialize built-in mode-specific gestures before loading JSON rules.
        self._initialize_mouse_mode()
        self._initialize_keyboard_mode()
        self._initialize_switch_mode()
        self.load_custom_rules("gesture_custom_rules.json")

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
            for switch_gesture in sorted_switch_gestures:
                if switch_gesture.update(hands_data):
                    return

        sorted_gestures = self._get_current_mode_sorted_gestures()
        high_priority_active = False
        active_priority = None

        for gesture in sorted_gestures:
            if (
                high_priority_active
                and active_priority is not None
                and gesture.priority < active_priority
            ):
                continue

            action_executed = gesture.update(
                hands_data, frame_capture_ts_ns=frame_capture_ts_ns
            )

            if getattr(gesture, "consumes_events", False) and gesture.is_active:
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

    def get_mode_name(self):
        return self.current_mode.value.upper()

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

    def load_custom_rules(self, path="gesture_custom_rules.json"):
        from backend.custom_rules.RuleCompiler import RuleCompiler
        from backend.custom_rules.RuleLoader import RuleLoader

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

        try:
            rules = RuleLoader(path).load()
        except Exception as exc:
            print(f"[WARN] Failed to load custom rules: {exc}")
            return

        compiler = RuleCompiler(self.config, self.screen_width, self.screen_height)
        global_cfg = rules.get("global", {})

        for rule in rules.get("custom_gestures", []):
            if not rule.get("enabled", False):
                continue

            mode_str = rule.get("mode", "mouse")
            if mode_str == "mouse":
                mode = ControlMode.MOUSE
            elif mode_str == "keyboard":
                mode = ControlMode.KEYBOARD
            else:
                mode = ControlMode.HOTKEY

            try:
                recognizer = compiler.compile_gesture(self.action, rule, global_cfg)
                self.add_custom_gesture(recognizer, mode=mode)
                self._custom_gesture_instances.append(recognizer)
                print(f"[OK] Loaded custom gesture: {rule.get('id')} ({mode_str})")
            except Exception as exc:
                print(f"[WARN] Skipped custom gesture {rule.get('id')}: {exc}")

        gesture_rule_by_id = {
            gesture["id"]: gesture
            for gesture in rules.get("custom_gestures", [])
            if gesture.get("enabled", False)
        }

        for macro in rules.get("custom_macros", []):
            if not macro.get("enabled", False):
                continue

            mode_str = macro.get("mode", "mouse")
            if mode_str == "mouse":
                mode = ControlMode.MOUSE
            elif mode_str == "keyboard":
                mode = ControlMode.KEYBOARD
            else:
                mode = ControlMode.HOTKEY

            try:
                recognizer = compiler.compile_macro(
                    self.action, macro, gesture_rule_by_id, global_cfg
                )
                self.add_custom_gesture(recognizer, mode=mode)
                self._custom_gesture_instances.append(recognizer)
                print(f"[OK] Loaded custom macro: {macro.get('id')} ({mode_str})")
            except Exception as exc:
                print(f"[WARN] Skipped custom macro {macro.get('id')}: {exc}")

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
