from backend.HandsData import HandsData
from backend.gestures.GestureRecognizer import SnapshotGestureRecognizer
from backend.gestures.GestureUtils import is_hand_fully_open, is_palm_facing_camera


class KeyboardModeEntryGesture(SnapshotGestureRecognizer):
    """
    Switch from MOUSE mode to KEYBOARD mode when both hands are fully open.
    """

    def __init__(
        self,
        action,
        strategizer,
        priority=20,
        extension_threshold=155.0,
        pending_frames=6,
        ending_frames=3,
    ):
        super().__init__(action, priority=priority, pending_frames=pending_frames, ending_frames=ending_frames)
        self.strategizer = strategizer
        self.extension_threshold = extension_threshold

    def detect_gesture(self, hands_data: HandsData):
        if self.strategizer.current_mode.value != "mouse":
            return False, None

        if not hands_data.wrist.has_left or not hands_data.wrist.has_right:
            return False, None

        left_open = is_hand_fully_open(hands_data.wrist.left, extension_threshold=self.extension_threshold)
        right_open = is_hand_fully_open(hands_data.wrist.right, extension_threshold=self.extension_threshold)
        if not left_open or not right_open:
            return False, None

        left_palm = is_palm_facing_camera(hands_data.camera.left)
        right_palm = is_palm_facing_camera(hands_data.camera.right)
        if not left_palm or not right_palm:
            return False, None

        return True, None

    def execute_action(self, data):
        from backend.Strategizer import ControlMode

        self.strategizer.set_mode(ControlMode.KEYBOARD)

