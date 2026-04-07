from backend.HandsData import HandsData
from backend.gestures.GestureRecognizer import SnapshotGestureRecognizer
from backend.gestures.GestureUtils import get_finger_angle, get_finger_extension, get_hand_openness


class KeyboardModeExitGesture(SnapshotGestureRecognizer):
    """
    Switch from KEYBOARD or HOTKEY mode to MOUSE mode when the right hand is a fist.
    """
    _MAX_THUMB_EXTENSION_RATIO = 0.98

    def __init__(
        self,
        action,
        strategizer,
        priority=20,
        pending_frames=5,
        ending_frames=3,
        extension_threshold=150.0,
        max_openness=0.16,
        max_extension_ratio=0.90,
        max_avg_finger_angle=145.0,
    ):
        super().__init__(action, priority=priority, pending_frames=pending_frames, ending_frames=ending_frames)
        self.strategizer = strategizer
        self.extension_threshold = extension_threshold
        self.max_openness = max_openness
        self.max_extension_ratio = max_extension_ratio
        self.max_avg_finger_angle = max_avg_finger_angle

    def _is_strict_fist(self, hand) -> bool:
        # Ignore thumb spread so resting it beside or in front of the fist does
        # not prevent keyboard exit, but still reject a clearly straight thumb.
        openness = get_hand_openness(hand, include_thumb=False)
        if openness > self.max_openness:
            return False

        # Finger base->tip straightness must also be small on all non-thumb fingers.
        finger_extensions = [
            get_finger_extension(hand.index),
            get_finger_extension(hand.middle),
            get_finger_extension(hand.ring),
            get_finger_extension(hand.pinky),
        ]
        if max(finger_extensions) > self.max_extension_ratio:
            return False
        if get_finger_extension(hand.thumb) > self._MAX_THUMB_EXTENSION_RATIO:
            return False

        finger_angles = [
            get_finger_angle(hand.index),
            get_finger_angle(hand.middle),
            get_finger_angle(hand.ring),
            get_finger_angle(hand.pinky),
        ]
        avg_angle = sum(finger_angles) / len(finger_angles)
        return avg_angle <= self.max_avg_finger_angle

    def detect_gesture(self, hands_data: HandsData):
        if self.strategizer.current_mode.value not in ("keyboard", "hotkey"):
            return False, None

        if not hands_data.wrist.has_right:
            return False, None

        right = hands_data.wrist.right
        right_fist = self._is_strict_fist(right)
        return right_fist, None

    def execute_action(self, data):
        from backend.Strategizer import ControlMode

        self.strategizer.set_mode(ControlMode.MOUSE)
