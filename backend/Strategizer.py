from backend.HandsData import HandsData
from enum import Enum


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
        # Add other mode initializations when they are implemented

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
        from backend.gestures.mouse_mode.MoveMouseGesture import MoveMouseGesture

    def set_mode(self, mode: ControlMode):
        """
        Change the current control mode.

        Args:
            mode: ControlMode to switch to
        """
        if mode != self.current_mode:
            # Reset all gestures in previous mode
            self._reset_current_mode_gestures()

            # Switch mode
            self.current_mode = mode
            print(f"Switched to {mode.value} mode")

    def _reset_current_mode_gestures(self):
        """Reset all gesture recognizers in the current mode"""
        for gesture in self._get_current_mode_gestures():
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
        # TODO make it loop through the switch mode gestures to see if it should switch the mode before doing the actual mode gestures

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
