from backend.gestures.GestureRecognizer import SnapshotGestureRecognizer
from backend.gestures.GestureUtils import are_fingers_pinched, camera_to_screen
from backend.HandsData import HandsData


class LeftClickGesture(SnapshotGestureRecognizer):
    """
    Detects thumb and middle finger pinch for left click.

    Activated when:
    - Thumb tip and middle finger tip are pinched together
    - Triggers once per pinch (debounced)

    Priority: High (overrides mouse tracking)
    """

    def __init__(self, action, screen_width, screen_height, priority, pinch_threshold,
                 extension_threshold, pending_frames, ending_frames):
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
        """
        super().__init__(action, priority, pending_frames, ending_frames)
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.pinch_threshold = pinch_threshold
        self.extension_threshold = extension_threshold

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

        # Get click position from index finger tip (where cursor should be)
        index_tip = hand_camera.index.tip
        if index_tip is None:
            return False, None

        # Convert to screen coordinates
        screen_x, screen_y = camera_to_screen(
            index_tip, self.screen_width, self.screen_height
        )

        return True, (screen_x, screen_y)

    def execute_action(self, data):
        """
        Perform left click at the cursor position.

        Args:
            data: Tuple (screen_x, screen_y)
        """
        if data is not None:
            screen_x, screen_y = data
            self.action.left_click(screen_x, screen_y)
