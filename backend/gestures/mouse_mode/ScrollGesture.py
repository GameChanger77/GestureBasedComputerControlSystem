import math

from backend.gestures.GestureRecognizer import ContinuousGestureRecognizer
from backend.gestures.GestureUtils import are_fingers_pinched, is_finger_extended
from backend.gestures.GestureStateMachine import GestureState
from backend.HandsData import HandsData


class ScrollGesture(ContinuousGestureRecognizer):
    """
    Detects two fingers extended (index + middle) for scrolling.

    Activated when:
    - ONLY index and middle fingers are extended (ring and pinky curled, thumb ignored)
    - Tracks vertical movement of fingers for scroll amount

    Priority: Medium (higher than mouse tracking, lower than clicks)
    """

    def __init__(
        self,
        action,
        priority,
        scroll_sensitivity,
        extension_threshold,
        pending_frames,
        ending_frames,
        pinch_threshold=0.45,
    ):
        """
        Args:
            action: Action object for executing scroll
            priority: Gesture priority (default=5, medium priority)
            scroll_sensitivity: Multiplier for scroll speed
            extension_threshold: Minimum joint angle in degrees to be extended
            pending_frames: Frames to confirm gesture
            ending_frames: Frames in ending state
        """
        super().__init__(action, priority, pending_frames, ending_frames)
        self.scroll_sensitivity = scroll_sensitivity
        self.extension_threshold = extension_threshold
        self.non_scroll_extension_threshold = min(179.0, float(extension_threshold) + 12.0)
        self.pinch_threshold = pinch_threshold
        self._last_y_position = None
        self._scroll_residual_y = 0.0
        self._frame_count = 0
        self.suppresses_lower_priorities_while_active = True

    def detect_gesture(self, hands_data: HandsData):
        """
        Detect if ONLY index and middle fingers are extended for scrolling.

        Returns:
            tuple: (detected, scroll_delta_y)
        """
        self._frame_count += 1

        if not hands_data.wrist.has_dominant or not hands_data.camera.has_dominant:
            self._last_y_position = None
            return False, None

        hand_wrist = hands_data.wrist.dominant
        hand_camera = hands_data.camera.dominant

        if not is_finger_extended(hand_wrist.index, threshold=self.extension_threshold):
            self._last_y_position = None
            self._scroll_residual_y = 0.0
            return False, None
        if not is_finger_extended(hand_wrist.middle, threshold=self.extension_threshold):
            self._last_y_position = None
            self._scroll_residual_y = 0.0
            return False, None
        if is_finger_extended(hand_wrist.ring, threshold=self.non_scroll_extension_threshold):
            self._last_y_position = None
            self._scroll_residual_y = 0.0
            return False, None
        if is_finger_extended(hand_wrist.pinky, threshold=self.non_scroll_extension_threshold):
            self._last_y_position = None
            self._scroll_residual_y = 0.0
            return False, None

        # Scroll should not overlap with click pinch poses.
        thumb_tip = hand_wrist.thumb.tip
        if are_fingers_pinched(thumb_tip, hand_wrist.middle.tip, self.pinch_threshold):
            self._last_y_position = None
            self._scroll_residual_y = 0.0
            return False, None
        if are_fingers_pinched(thumb_tip, hand_wrist.ring.tip, self.pinch_threshold):
            self._last_y_position = None
            self._scroll_residual_y = 0.0
            return False, None

        # Get average Y position of the two fingers for scroll tracking
        index_tip = hand_camera.index.tip
        middle_tip = hand_camera.middle.tip

        if index_tip is None or middle_tip is None:
            self._last_y_position = None
            return False, None

        # Calculate average Y position
        current_y = (index_tip[1] + middle_tip[1]) / 2.0

        # Calculate scroll delta if we have a previous position
        scroll_delta_y = 0
        if self._last_y_position is not None:
            raw_delta = current_y - self._last_y_position
            self._scroll_residual_y += raw_delta * self.scroll_sensitivity
            if self._scroll_residual_y >= 1.0:
                scroll_delta_y = int(math.floor(self._scroll_residual_y))
            elif self._scroll_residual_y <= -1.0:
                scroll_delta_y = int(math.ceil(self._scroll_residual_y))
            if scroll_delta_y != 0:
                self._scroll_residual_y -= scroll_delta_y

        # Update last position
        self._last_y_position = current_y

        return True, scroll_delta_y

    def update(self, hands_data: HandsData, frame_capture_ts_ns=None):
        detected, gesture_data = self.detect_gesture(hands_data)

        if detected and frame_capture_ts_ns is not None:
            self.action.set_pending_latency_origin_ts_ns(frame_capture_ts_ns)

        state, should_trigger, data = self.state_machine.update(detected, gesture_data)
        action_executed = False
        note = ""

        if should_trigger and data:
            self.action.scroll(delta_x=0, delta_y=data)
            action_executed = True
            note = f"Scroll delta {int(data)} (residual {self._scroll_residual_y:.2f})"
        elif state == GestureState.ACTIVE and detected:
            note = f"Tracking scroll pose (residual {self._scroll_residual_y:.2f})"
        elif not detected:
            note = "Scroll pose not detected"

        self._set_debug_frame(
            detected=detected,
            should_trigger=should_trigger,
            action_executed=action_executed,
            state=state,
            note=note,
        )
        return action_executed

    def execute_action(self, data):
        pass

    def reset(self):
        """Reset gesture state and clear position tracking"""
        super().reset()
        self._last_y_position = None
        self._scroll_residual_y = 0.0
