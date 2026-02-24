import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from backend.HandsData import HandsData
from backend.gestures.switch_mode.KeyboardModeEntryGesture import KeyboardModeEntryGesture
from backend.gestures.switch_mode.KeyboardModeExitGesture import KeyboardModeExitGesture


class _ActionStub:
    pass


class _StrategizerStub:
    def __init__(self, mode_value: str):
        self.current_mode = SimpleNamespace(value=mode_value)
        self.mode_set_to = None

    def set_mode(self, mode):
        self.mode_set_to = mode


def _hands(right: bool, left: bool = False) -> HandsData:
    wrist = {}
    camera = {}
    if right:
        wrist["Right"] = np.zeros((21, 3), dtype=np.float32)
        camera["Right"] = np.zeros((21, 3), dtype=np.float32)
    if left:
        wrist["Left"] = np.zeros((21, 3), dtype=np.float32)
        camera["Left"] = np.zeros((21, 3), dtype=np.float32)
    return HandsData(wrist, camera)


class ModeSwitchRightHandTests(unittest.TestCase):
    def test_entry_uses_right_hand_open_only(self):
        strategizer = _StrategizerStub("mouse")
        gesture = KeyboardModeEntryGesture(_ActionStub(), strategizer=strategizer)
        with patch(
            "backend.gestures.switch_mode.KeyboardModeEntryGesture.is_hand_fully_open",
            return_value=True,
        ):
            detected, _ = gesture.detect_gesture(_hands(right=True, left=False))
        self.assertTrue(detected)

    def test_entry_rejects_when_not_mouse_mode(self):
        strategizer = _StrategizerStub("keyboard")
        gesture = KeyboardModeEntryGesture(_ActionStub(), strategizer=strategizer)
        with patch(
            "backend.gestures.switch_mode.KeyboardModeEntryGesture.is_hand_fully_open",
            return_value=True,
        ):
            detected, _ = gesture.detect_gesture(_hands(right=True, left=False))
        self.assertFalse(detected)

    def test_entry_rejects_when_right_hand_missing(self):
        strategizer = _StrategizerStub("mouse")
        gesture = KeyboardModeEntryGesture(_ActionStub(), strategizer=strategizer)
        with patch(
            "backend.gestures.switch_mode.KeyboardModeEntryGesture.is_hand_fully_open",
            return_value=True,
        ):
            detected, _ = gesture.detect_gesture(_hands(right=False, left=True))
        self.assertFalse(detected)

    def test_exit_uses_right_hand_fist_only(self):
        strategizer = _StrategizerStub("keyboard")
        gesture = KeyboardModeExitGesture(_ActionStub(), strategizer=strategizer)
        with patch.object(gesture, "_is_strict_fist", return_value=True):
            detected, _ = gesture.detect_gesture(_hands(right=True, left=False))
        self.assertTrue(detected)

    def test_exit_rejects_when_not_keyboard_mode(self):
        strategizer = _StrategizerStub("mouse")
        gesture = KeyboardModeExitGesture(_ActionStub(), strategizer=strategizer)
        with patch.object(gesture, "_is_strict_fist", return_value=True):
            detected, _ = gesture.detect_gesture(_hands(right=True, left=False))
        self.assertFalse(detected)

    def test_exit_rejects_when_right_hand_missing(self):
        strategizer = _StrategizerStub("keyboard")
        gesture = KeyboardModeExitGesture(_ActionStub(), strategizer=strategizer)
        with patch.object(gesture, "_is_strict_fist", return_value=True):
            detected, _ = gesture.detect_gesture(_hands(right=False, left=True))
        self.assertFalse(detected)


if __name__ == "__main__":
    unittest.main()

