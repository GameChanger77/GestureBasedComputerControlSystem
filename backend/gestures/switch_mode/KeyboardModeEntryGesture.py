from backend.HandsData import HandsData
from backend.gestures.GestureRecognizer import SnapshotGestureRecognizer
from backend.gestures.GestureUtils import is_hand_fully_open


class KeyboardModeEntryGesture(SnapshotGestureRecognizer):
    """
    Switch from MOUSE or HOTKEY mode to KEYBOARD mode when the dominant hand
    shows an open palm toward the camera with all fingers extended.
    """

    def __init__(
        self,
        action,
        strategizer,
        priority=20,
        extension_threshold=155.0,
        min_palm_normal_z=0.35,
        pending_frames=6,
        ending_frames=3,
    ):
        super().__init__(action, priority=priority, pending_frames=pending_frames, ending_frames=ending_frames)
        self.strategizer = strategizer
        self.extension_threshold = extension_threshold
        self.min_palm_normal_z = min_palm_normal_z

    def detect_gesture(self, hands_data: HandsData):
        if self.strategizer.current_mode.value not in ("mouse", "hotkey"):
            return False, None

        if not hands_data.wrist.has_dominant:
            return False, None

        dominant_open = is_hand_fully_open(
            hands_data.wrist.dominant,
            extension_threshold=self.extension_threshold,
            min_extended_fingers=5,
            require_palm_facing_camera=True,
            min_palm_normal_z=self.min_palm_normal_z,
        )
        if not dominant_open:
            return False, None

        return True, None

    def execute_action(self, data):
        from backend.Strategizer import ControlMode

        self.strategizer.set_mode(ControlMode.KEYBOARD)
