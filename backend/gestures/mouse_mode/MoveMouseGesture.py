from backend.gestures.GestureRecognizer import ContinuousGestureRecognizer
from backend.gestures.GestureUtils import are_only_fingers_extended, camera_to_screen
from backend.HandsData import HandsData
import time


class MoveMouseGesture(ContinuousGestureRecognizer):
    """
    Tracks the index finger tip to control mouse movement.

    Activated when:
    - ONLY index finger is extended (all others curled, thumb ignored)
    - Tracks continuously while only index remains extended

    Priority: Low (so other gestures can override)
    """

    def __init__(
        self,
        action,
        screen_width,
        screen_height,
        priority,
        extension_threshold,
        pending_frames,
        ending_frames,
        min_delta_px=2,
        cadence_ms=75,
    ):
        """
        Args:
            action: Action object for executing mouse moves
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            priority: Gesture priority (default=1, low priority)
            extension_threshold: Minimum joint angle in degrees to be extended (default=155°)
            pending_frames: Frames to confirm gesture
            ending_frames: Frames in ending state
        """
        super().__init__(action, priority, pending_frames, ending_frames)
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.extension_threshold = extension_threshold
        self.min_delta_px = max(0, int(min_delta_px))
        self.cadence_ns = max(1, int(cadence_ms)) * 1_000_000
        self._frame_count = 0
        self._last_emitted_pos = None
        self._last_emit_ts_ns = 0

    def detect_gesture(self, hands_data: HandsData):
        """
        Detect if ONLY index finger is extended for mouse tracking.

        Returns:
            tuple: (detected, (screen_x, screen_y))
        """
        self._frame_count += 1

        if not hands_data.wrist.has_right or not hands_data.camera.has_right:
            return False, None
        hand_wrist = hands_data.wrist.right
        hand_camera = hands_data.camera.right

        # Check if ONLY index finger is extended (others must be curled)
        detected = are_only_fingers_extended(hand_wrist, ['index'], self.extension_threshold)

        if not detected:
            return False, None

        # Get index finger tip in camera coordinates
        index_tip = hand_camera.index.tip
        if index_tip is None:
            return False, None

        # Convert to screen coordinates
        screen_x, screen_y = camera_to_screen(index_tip, self.screen_width, self.screen_height)

        return True, (screen_x, screen_y)

    def execute_action(self, data):
        """
        Move mouse to the index finger tip position.

        Args:
            data: Tuple (screen_x, screen_y)
        """
        if data is not None:
            screen_x, screen_y = data
            now_ns = time.perf_counter_ns()

            if self._last_emitted_pos is None:
                should_emit = True
            else:
                last_x, last_y = self._last_emitted_pos
                delta_x = abs(screen_x - last_x)
                delta_y = abs(screen_y - last_y)
                delta_exceeded = delta_x >= self.min_delta_px or delta_y >= self.min_delta_px
                cadence_elapsed = (now_ns - self._last_emit_ts_ns) >= self.cadence_ns
                should_emit = delta_exceeded or cadence_elapsed

            if should_emit:
                self.action.move_cursor(screen_x, screen_y)
                self._last_emitted_pos = (screen_x, screen_y)
                self._last_emit_ts_ns = now_ns

    def reset(self):
        """Reset gesture state and cursor throttling state."""
        super().reset()
        self._last_emitted_pos = None
        self._last_emit_ts_ns = 0
