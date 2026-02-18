from backend.HandsData import HandsData
from enum import Enum
import time


class ControlMode(Enum):
    IDLE = "idle"
    MOUSE = "mouse"
    KEYBOARD = "keyboard"
    HOTKEY = "hotkey"


class Strategizer:

    def __init__(self, action, config, screen_width, screen_height):
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

        # Default mode is mouse mode (Can be changed for easier manual testing)
        self.current_mode = ControlMode.MOUSE

        # Gesture recognizers for each mode
        self.switch_mode_gestures = []
        self.mouse_mode_gestures = []
        self.keyboard_mode_gestures = []
        self.hotkey_mode_gestures = []

        # Initialize mode-specific gestures
        self._initialize_mouse_mode()
        self._initialize_keyboard_mode()
        self._initialize_switch_mode()
        self._last_mode_switch_ts = 0.0

    def _initialize_mouse_mode(self):
        """Initialize gesture recognizers for mouse mode"""
        from backend.gestures.mouse_mode.MoveMouseGesture import MoveMouseGesture
        from backend.gestures.mouse_mode.LeftClickGesture import LeftClickGesture
        from backend.gestures.mouse_mode.RightClickGesture import RightClickGesture
        from backend.gestures.mouse_mode.ScrollGesture import ScrollGesture

        # Get config values
        finger_angle = self.config['finger_extension_angle']
        scroll_sens = self.config['scroll_sensitivity']
        pinch_thresh = self.config['pinch_threshold']
        mouse_pending = self.config['mouse_tracking_pending_frames']
        click_pending = self.config['click_pending_frames']
        scroll_pending = self.config['scroll_pending_frames']
        ending = self.config['ending_frames']

        # Create mouse mode gestures
        # Priority order: Clicks (10) > Scroll (5) > Mouse tracking (1)
        self.mouse_mode_gestures = [
            LeftClickGesture(
                self.action, self.screen_width, self.screen_height,
                priority=10,
                pinch_threshold=pinch_thresh,
                extension_threshold=finger_angle,
                pending_frames=click_pending,
                ending_frames=ending
            ),
            RightClickGesture(
                self.action, self.screen_width, self.screen_height,
                priority=10,
                pinch_threshold=pinch_thresh,
                extension_threshold=finger_angle,
                pending_frames=click_pending,
                ending_frames=ending
            ),
            ScrollGesture(
                self.action,
                priority=5,
                scroll_sensitivity=scroll_sens,
                extension_threshold=finger_angle,
                pending_frames=scroll_pending,
                ending_frames=ending
            ),
            MoveMouseGesture(
                self.action, self.screen_width, self.screen_height,
                priority=1,
                extension_threshold=finger_angle,
                pending_frames=mouse_pending,
                ending_frames=ending
            ),
        ]

    def _initialize_switch_mode(self):
        """Initialize gesture recognizers for switching from one mode to another"""
        from backend.gestures.switch_mode.KeyboardModeEntryGesture import KeyboardModeEntryGesture
        from backend.gestures.switch_mode.KeyboardModeExitGesture import KeyboardModeExitGesture

        finger_angle = self.config['finger_extension_angle']
        entry_pending = self.config.get("keyboard_mode_entry_pending_frames", 6)
        exit_pending = self.config.get("keyboard_mode_exit_pending_frames", 5)
        exit_angle = self.config.get("keyboard_mode_exit_extension_angle", 150.0)
        exit_max_openness = self.config.get("keyboard_mode_exit_max_openness", 0.16)
        exit_max_extension = self.config.get("keyboard_mode_exit_max_extension_ratio", 0.90)
        exit_max_avg_angle = self.config.get("keyboard_mode_exit_max_avg_finger_angle", 145.0)
        ending = self.config['ending_frames']

        self.switch_mode_gestures = [
            KeyboardModeEntryGesture(
                self.action,
                strategizer=self,
                priority=20,
                extension_threshold=finger_angle,
                pending_frames=entry_pending,
                ending_frames=ending,
            ),
            KeyboardModeExitGesture(
                self.action,
                strategizer=self,
                priority=20,
                pending_frames=exit_pending,
                ending_frames=ending,
                extension_threshold=exit_angle,
                max_openness=exit_max_openness,
                max_extension_ratio=exit_max_extension,
                max_avg_finger_angle=exit_max_avg_angle,
            ),
        ]

    def _initialize_keyboard_mode(self):
        """Initialize gesture recognizers for keyboard mode."""
        from backend.gestures.keyboard_mode.AirTypingGesture import AirTypingGesture

        self.keyboard_mode_gestures = [
            AirTypingGesture(
                self.action,
                config=self.config,
                priority=15,
            )
        ]

    def set_mode(self, mode: ControlMode):
        """
        Change the current control mode.

        Args:
            mode: ControlMode to switch to
        """
        if mode != self.current_mode:
            # Reset all gestures in previous mode
            self._reset_current_mode_gestures()

            # Always release held keys on mode change for safety
            if hasattr(self.action, "release_all_keys"):
                self.action.release_all_keys()

            # Switch mode
            self.current_mode = mode
            self._last_mode_switch_ts = time.time()
            self._reset_mode_gestures(mode)
            print(f"Switched to {mode.value} mode")

    def _reset_current_mode_gestures(self):
        """Reset all gesture recognizers in the current mode"""
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
        """Get gesture recognizers for the current mode"""
        if self.current_mode == ControlMode.MOUSE:
            return self.mouse_mode_gestures
        elif self.current_mode == ControlMode.KEYBOARD:
            return self.keyboard_mode_gestures
        elif self.current_mode == ControlMode.HOTKEY:
            return self.hotkey_mode_gestures
        return []

    def strategize(self, hands_data: HandsData):
        """
        Update all gesture recognizers for the current mode.

        Uses priority-based conflict resolution:
        - Higher priority gestures are checked first
        - Once a high-priority gesture is active, lower-priority gestures are skipped

        Args:
            hands_data: Current hand landmark data
        """
        mode_switch_cooldown = self.config.get("keyboard_mode_switch_cooldown_sec", 1.0)
        elapsed_since_switch = time.time() - self._last_mode_switch_ts

        # Evaluate mode-switch gestures first (highest priority globally),
        # but apply a short cooldown to prevent immediate bounce between modes.
        if elapsed_since_switch >= mode_switch_cooldown:
            for switch_gesture in sorted(self.switch_mode_gestures, key=lambda g: g.priority, reverse=True):
                switched = switch_gesture.update(hands_data)
                if switched:
                    # Skip frame after a mode switch to avoid accidental cross-mode action.
                    return

        current_gestures = self._get_current_mode_gestures()

        # Sort gestures by priority (highest first)
        sorted_gestures = sorted(current_gestures, key=lambda g: g.priority, reverse=True)

        # Track if any high-priority gesture is active
        high_priority_active = False

        for gesture in sorted_gestures:
            # Skip low-priority gestures if a high-priority one is active
            if high_priority_active and gesture.priority < 5:
                continue

            # Update gesture
            action_executed = gesture.update(hands_data)

            # If a high-priority gesture executed an action, prevent lower-priority gestures
            if action_executed and gesture.priority >= 5:
                high_priority_active = True

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
        elif mode == ControlMode.KEYBOARD:
            self.keyboard_mode_gestures.append(gesture)
        elif mode == ControlMode.HOTKEY:
            self.hotkey_mode_gestures.append(gesture)

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
        elif mode == ControlMode.KEYBOARD and gesture in self.keyboard_mode_gestures:
            self.keyboard_mode_gestures.remove(gesture)
        elif mode == ControlMode.HOTKEY and gesture in self.hotkey_mode_gestures:
            self.hotkey_mode_gestures.remove(gesture)
