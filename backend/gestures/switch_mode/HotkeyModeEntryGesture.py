from backend.HandsData import HandsData
from backend.gestures.GestureRecognizer import SnapshotGestureRecognizer
from backend.gestures.GestureUtils import are_fingers_pinched, is_finger_extended


class HotkeyModeEntryGesture(SnapshotGestureRecognizer):
    """
    Switch from MOUSE or KEYBOARD mode to HOTKEY mode when the right hand forms an OK sign.
    """

    def __init__(
        self,
        action,
        strategizer,
        priority=20,
        pinch_threshold=0.30,
        extension_threshold=155.0,
        pending_frames=6,
        ending_frames=3,
    ):
        super().__init__(
            action,
            priority=priority,
            pending_frames=pending_frames,
            ending_frames=ending_frames,
        )
        self.strategizer = strategizer
        self.pinch_threshold = pinch_threshold
        self.extension_threshold = extension_threshold

    def _is_ok_sign(self, hand) -> bool:
        if hand is None or not hand.exists:
            return False

        if not are_fingers_pinched(hand.thumb.tip, hand.index.tip, self.pinch_threshold):
            return False

        return all(
            is_finger_extended(finger, threshold=self.extension_threshold)
            for finger in (hand.middle, hand.ring, hand.pinky)
        )

    def detect_gesture(self, hands_data: HandsData):
        if self.strategizer.current_mode.value not in ("mouse", "keyboard"):
            return False, None

        if not hands_data.wrist.has_right:
            return False, None

        return self._is_ok_sign(hands_data.wrist.right), None

    def execute_action(self, data):
        from backend.Strategizer import ControlMode

        self.strategizer.set_mode(ControlMode.HOTKEY)
