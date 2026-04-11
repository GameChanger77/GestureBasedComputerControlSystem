import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from backend.HandsData import HandsData
from backend.gestures.switch_mode.HotkeyModeEntryGesture import HotkeyModeEntryGesture
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
        ) as open_mock:
            detected, _ = gesture.detect_gesture(_hands(right=True, left=False))
        self.assertTrue(detected)
        open_mock.assert_called_once_with(
            unittest.mock.ANY,
            extension_threshold=gesture.extension_threshold,
            min_extended_fingers=5,
            require_palm_facing_camera=True,
            min_palm_normal_z=gesture.min_palm_normal_z,
        )

    def test_entry_uses_right_hand_open_from_hotkey_mode(self):
        strategizer = _StrategizerStub("hotkey")
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

    def test_exit_uses_right_hand_fist_from_hotkey_mode(self):
        strategizer = _StrategizerStub("hotkey")
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

    def test_exit_strict_fist_ignores_thumb_spread_when_thumb_not_extended(self):
        strategizer = _StrategizerStub("keyboard")
        gesture = KeyboardModeExitGesture(_ActionStub(), strategizer=strategizer)
        hand = SimpleNamespace(
            exists=True,
            thumb=SimpleNamespace(),
            index=SimpleNamespace(),
            middle=SimpleNamespace(),
            ring=SimpleNamespace(),
            pinky=SimpleNamespace(),
        )

        with patch(
            "backend.gestures.switch_mode.KeyboardModeExitGesture.get_hand_openness",
            return_value=0.05,
        ) as openness_mock, patch(
            "backend.gestures.switch_mode.KeyboardModeExitGesture.get_finger_extension",
            side_effect=[0.20, 0.22, 0.24, 0.21, 0.40],
        ), patch(
            "backend.gestures.switch_mode.KeyboardModeExitGesture.get_finger_angle",
            side_effect=[100.0, 105.0, 102.0, 98.0],
        ):
            self.assertTrue(gesture._is_strict_fist(hand))

        openness_mock.assert_called_once_with(hand, include_thumb=False)

    def test_exit_strict_fist_allows_thumb_that_is_not_fully_extended(self):
        strategizer = _StrategizerStub("keyboard")
        gesture = KeyboardModeExitGesture(_ActionStub(), strategizer=strategizer)
        hand = SimpleNamespace(
            exists=True,
            thumb=SimpleNamespace(),
            index=SimpleNamespace(),
            middle=SimpleNamespace(),
            ring=SimpleNamespace(),
            pinky=SimpleNamespace(),
        )

        with patch(
            "backend.gestures.switch_mode.KeyboardModeExitGesture.get_hand_openness",
            return_value=0.05,
        ), patch(
            "backend.gestures.switch_mode.KeyboardModeExitGesture.get_finger_extension",
            side_effect=[0.20, 0.22, 0.24, 0.21, 0.95],
        ), patch(
            "backend.gestures.switch_mode.KeyboardModeExitGesture.get_finger_angle",
            side_effect=[100.0, 105.0, 102.0, 98.0],
        ):
            self.assertTrue(gesture._is_strict_fist(hand))

    def test_exit_strict_fist_rejects_clearly_extended_thumb(self):
        strategizer = _StrategizerStub("keyboard")
        gesture = KeyboardModeExitGesture(_ActionStub(), strategizer=strategizer)
        hand = SimpleNamespace(
            exists=True,
            thumb=SimpleNamespace(),
            index=SimpleNamespace(),
            middle=SimpleNamespace(),
            ring=SimpleNamespace(),
            pinky=SimpleNamespace(),
        )

        with patch(
            "backend.gestures.switch_mode.KeyboardModeExitGesture.get_hand_openness",
            return_value=0.05,
        ), patch(
            "backend.gestures.switch_mode.KeyboardModeExitGesture.get_finger_extension",
            side_effect=[0.20, 0.22, 0.24, 0.21, 0.995],
        ), patch(
            "backend.gestures.switch_mode.KeyboardModeExitGesture.get_finger_angle",
            side_effect=[100.0, 105.0, 102.0, 98.0],
        ):
            self.assertFalse(gesture._is_strict_fist(hand))

    def test_hotkey_entry_uses_ok_sign_from_mouse_mode(self):
        strategizer = _StrategizerStub("mouse")
        gesture = HotkeyModeEntryGesture(_ActionStub(), strategizer=strategizer)
        with patch.object(gesture, "_is_ok_sign", return_value=True):
            detected, _ = gesture.detect_gesture(_hands(right=True, left=False))
        self.assertTrue(detected)

    def test_hotkey_entry_uses_ok_sign_from_keyboard_mode(self):
        strategizer = _StrategizerStub("keyboard")
        gesture = HotkeyModeEntryGesture(_ActionStub(), strategizer=strategizer)
        with patch.object(gesture, "_is_ok_sign", return_value=True):
            detected, _ = gesture.detect_gesture(_hands(right=True, left=False))
        self.assertTrue(detected)

    def test_hotkey_entry_rejects_when_already_hotkey_mode(self):
        strategizer = _StrategizerStub("hotkey")
        gesture = HotkeyModeEntryGesture(_ActionStub(), strategizer=strategizer)
        with patch.object(gesture, "_is_ok_sign", return_value=True):
            detected, _ = gesture.detect_gesture(_hands(right=True, left=False))
        self.assertFalse(detected)

    def test_hotkey_entry_rejects_when_right_hand_missing(self):
        strategizer = _StrategizerStub("mouse")
        gesture = HotkeyModeEntryGesture(_ActionStub(), strategizer=strategizer)
        with patch.object(gesture, "_is_ok_sign", return_value=True):
            detected, _ = gesture.detect_gesture(_hands(right=False, left=True))
        self.assertFalse(detected)

    def test_hotkey_entry_defaults_to_three_pending_frames(self):
        strategizer = _StrategizerStub("mouse")
        gesture = HotkeyModeEntryGesture(_ActionStub(), strategizer=strategizer)
        self.assertEqual(gesture.state_machine.pending_frames, 3)


if __name__ == "__main__":
    unittest.main()
