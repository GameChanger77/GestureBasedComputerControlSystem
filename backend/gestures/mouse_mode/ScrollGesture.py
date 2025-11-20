from backend.gestures.GestureRecognizer import ContinuousGestureRecognizer
from backend.gestures.GestureUtils import are_only_fingers_extended
from backend.HandsData import HandsData


class ScrollGesture(ContinuousGestureRecognizer):
    """
    Detects two fingers extended (index + middle) for scrolling.

    Activated when:
    - ONLY index and middle fingers are extended (ring and pinky curled, thumb ignored)
    - Tracks vertical movement of fingers for scroll amount

    Priority: Medium (higher than mouse tracking, lower than clicks)
    """

    def __init__(self, action, priority, scroll_sensitivity, extension_threshold,
                 pending_frames, ending_frames):
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
        self._last_y_position = None
        self._frame_count = 0

    def detect_gesture(self, hands_data: HandsData):
        """
        Detect if ONLY index and middle fingers are extended for scrolling.

        Returns:
            tuple: (detected, scroll_delta_y)
        """
        self._frame_count += 1

        # Use right hand for mouse control
        if not hands_data.wrist.has_right or not hands_data.camera.has_right:
            self._last_y_position = None
            return False, None

        hand_wrist = hands_data.wrist.right
        hand_camera = hands_data.camera.right

        # Check if ONLY index and middle fingers are extended (ring and pinky must be curled)
        detected = are_only_fingers_extended(hand_wrist, ['index', 'middle'], self.extension_threshold)

        if not detected:
            self._last_y_position = None
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
            # Delta is inverted: moving hand down = scroll down (positive)
            # Camera Y increases as hand moves down, so we don't invert
            raw_delta = current_y - self._last_y_position
            delta = raw_delta * self.scroll_sensitivity
            scroll_delta_y = int(delta)

        # Update last position
        self._last_y_position = current_y

        return True, scroll_delta_y

    def execute_action(self, data):
        """
        Perform scroll based on finger movement.

        Args:
            data: Scroll delta (int)
        """
        if data is not None and data != 0:
            # Scroll vertically (delta_x=0, delta_y=data)
            self.action.scroll(delta_x=0, delta_y=data)

    def reset(self):
        """Reset gesture state and clear position tracking"""
        super().reset()
        self._last_y_position = None
