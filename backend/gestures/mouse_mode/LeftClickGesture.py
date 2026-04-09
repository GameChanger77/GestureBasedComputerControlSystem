from backend.gestures.GestureRecognizer import SnapshotGestureRecognizer
from backend.gestures.GestureUtils import are_fingers_pinched, camera_to_screen, is_finger_extended
from backend.HandsData import HandsData
from backend.gestures.GestureStateMachine import GestureState
import time


class LeftClickGesture(SnapshotGestureRecognizer):
    """
    Detects thumb and middle finger pinch for left click.

    Activated when:
    - Thumb tip and middle finger tip are pinched together
    - Confirmed pinch = single click immediately
    - Sustained hold = one additional click

    Priority: High (overrides mouse tracking)
    """

    def __init__(self, action, screen_width, screen_height, priority, pinch_threshold,
                 extension_threshold, pending_frames, ending_frames, double_click_hold_time=1.0):
        """
        Args:
            action: Action object for executing clicks
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            priority: Gesture priority (default=10, high priority)
            pinch_threshold: Distance threshold for pinch detection
            extension_threshold: Angle threshold for finger extension
            pending_frames: Frames to confirm gesture
            ending_frames: Frames in ending state
            double_click_hold_time: Time to hold pinch for double-click (seconds)
        """
        super().__init__(action, priority, pending_frames, ending_frames)
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.pinch_threshold = pinch_threshold
        self.extension_threshold = extension_threshold
        self.thumb_extension_threshold = max(110.0, float(extension_threshold) - 25.0)
        self.double_click_hold_time = double_click_hold_time
        self.suppresses_lower_priorities_while_active = True

        # Track when gesture became active for hold detection.
        self.gesture_start_time = None
        self.hold_click_triggered = False
        self.click_position = None

    def detect_gesture(self, hands_data: HandsData):
        """
        Detect if thumb and middle finger are pinched.

        Returns:
            tuple: (detected, (screen_x, screen_y))
        """
        # Use right hand for mouse control
        if not hands_data.wrist.has_right or not hands_data.camera.has_right:
            return False, None

        hand_wrist = hands_data.wrist.right
        hand_camera = hands_data.camera.right

        # Check if thumb and middle finger are pinched
        thumb_tip = hand_wrist.thumb.tip
        middle_tip = hand_wrist.middle.tip

        if not are_fingers_pinched(thumb_tip, middle_tip, self.pinch_threshold):
            return False, None

        if not is_finger_extended(hand_wrist.thumb, threshold=self.thumb_extension_threshold):
            return False, None

        # Left click should not overlap with scroll/open-finger poses.
        if is_finger_extended(hand_wrist.ring, threshold=self.extension_threshold):
            return False, None
        if is_finger_extended(hand_wrist.pinky, threshold=self.extension_threshold):
            return False, None

        # Get click position from index finger tip (where cursor should be)
        index_tip = hand_camera.index.tip
        if index_tip is None:
            return False, None

        # Convert to screen coordinates
        screen_x, screen_y = camera_to_screen(index_tip, self.screen_width, self.screen_height)

        return True, (screen_x, screen_y)

    def update(self, hands_data: HandsData, frame_capture_ts_ns=None):
        """
        Override update to handle hold-for-double-click logic.
        """
        detected, gesture_data = self.detect_gesture(hands_data)
        action_executed = False
        note = ""

        if detected and self.state_machine.is_idle and frame_capture_ts_ns is not None:
            self.action.set_pending_latency_origin_ts_ns(frame_capture_ts_ns)

        state, should_trigger, data = self.state_machine.update(detected, gesture_data)

        # Trigger single click as soon as the gesture is confirmed.
        if state == GestureState.ACTIVE and self.gesture_start_time is None:
            self.gesture_start_time = time.time()
            self.hold_click_triggered = False
            self.click_position = data
            if not self._already_triggered:
                self._already_triggered = True
                self.execute_single_click(self.click_position)
                action_executed = True
                note = "Single click triggered"
                self._set_debug_frame(
                    detected=detected,
                    should_trigger=should_trigger,
                    action_executed=action_executed,
                    state=state,
                    note=note,
                )
                return True

        # A sustained hold emits one additional click.
        if state == GestureState.ACTIVE and self.gesture_start_time is not None:
            hold_duration = time.time() - self.gesture_start_time

            if hold_duration >= self.double_click_hold_time and not self.hold_click_triggered:
                self.hold_click_triggered = True
                self.execute_single_click(self.click_position)
                action_executed = True
                note = "Hold click triggered"
                self._set_debug_frame(
                    detected=detected,
                    should_trigger=should_trigger,
                    action_executed=action_executed,
                    state=state,
                    note=note,
                )
                return True
            if not self.hold_click_triggered:
                note = "Hold for second click"

        # Releasing the gesture only resets the gesture state.
        if state == GestureState.IDLE and self.gesture_start_time is not None:
            note = "Released"
            self.gesture_start_time = None
            self.hold_click_triggered = False
            self.click_position = None
            self._already_triggered = False

        self._set_debug_frame(
            detected=detected,
            should_trigger=should_trigger,
            action_executed=action_executed,
            state=state,
            note=note,
        )
        return action_executed

    def execute_single_click(self, data):
        """Perform single click."""
        if data is not None:
            screen_x, screen_y = data
            self.action.left_click(screen_x, screen_y)

    def execute_action(self, data):
        """
        This method is overridden by update() to handle hold timing.
        """
        pass
