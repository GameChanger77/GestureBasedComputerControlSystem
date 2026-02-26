import unittest

import numpy as np

from backend.HandsData import HandsData
from backend.gestures.keyboard_mode.AirTypingGesture import AirTypingGesture


class _FakeAction:
    def __init__(self):
        self.tapped = []
        self.hotkeys = []
        self.typed_text = []

    def tap_key(self, key_code):
        self.tapped.append(key_code)

    def tap_hotkey(self, key_codes):
        self.hotkeys.append(list(key_codes))

    def type_text(self, text):
        self.typed_text.append(text)

    def release_all_keys(self):
        return


def _make_camera_hand(wrist_x: float, index_x: float, index_y: float = 0.42) -> np.ndarray:
    arr = np.zeros((21, 3), dtype=np.float32)
    wrist = np.array([wrist_x, 0.55, 0.0], dtype=np.float32)
    arr[0] = wrist

    arr[4] = wrist + np.array([-0.06, -0.08, 0.0], dtype=np.float32)
    arr[8] = np.array([index_x, index_y, 0.0], dtype=np.float32)
    arr[12] = wrist + np.array([0.04, -0.13, 0.0], dtype=np.float32)
    arr[16] = wrist + np.array([0.06, -0.11, 0.0], dtype=np.float32)
    arr[20] = wrist + np.array([0.08, -0.09, 0.0], dtype=np.float32)
    return arr


def _make_wrist_hand(pinch: bool) -> np.ndarray:
    arr = np.zeros((21, 3), dtype=np.float32)
    arr[0] = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    arr[4] = np.array([0.02, 0.0, 0.0], dtype=np.float32)
    arr[12] = np.array([0.03 if pinch else 0.70, 0.0, 0.0], dtype=np.float32)
    return arr


def _make_hands_data(
    *,
    right_present: bool = True,
    right_pinch: bool = False,
    right_index_x: float = 0.74,
    right_index_y: float = 0.42,
    right_wrist_x: float = 0.78,
) -> HandsData:
    camera = {}
    wrist = {}
    if right_present:
        camera["Right"] = _make_camera_hand(right_wrist_x, right_index_x, right_index_y)
        wrist["Right"] = _make_wrist_hand(right_pinch)
    return HandsData(wrist, camera)


class AirTypingSuggestionTests(unittest.TestCase):
    def setUp(self):
        self.action = _FakeAction()
        self.config = {
            "keyboard_swipe_min_points": 3,
            "keyboard_swipe_min_unique_keys": 3,
            "keyboard_swipe_release_pending_frames": 1,
            "keyboard_swipe_tracking_grace_frames": 2,
            "pinch_threshold": 0.15,
            "keyboard_flip_x_for_mapping": False,
        }
        self.gesture = AirTypingGesture(self.action, config=self.config, priority=15)
        # Hardcoded resume_stability_frames=4 in gesture; warm up once for deterministic tests.
        for _ in range(4):
            self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.74))
        self.gesture._swipe_decoder.decode = lambda trace, top_k=8: (
            "hello",
            0.92,
            ["hello", "help", "held", "helm", "hero"],
        )
        self.gesture._map_tip_to_slot = lambda side, tip, frame: (
            {"id": "h"} if tip[0] < 0.64 else
            {"id": "e"} if tip[0] < 0.68 else
            {"id": "l"} if tip[0] < 0.74 else
            {"id": "o"}
        )

    def _commit_swipe_word(self):
        for x in [0.62, 0.66, 0.70, 0.76]:
            self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=x))
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.76))

    def test_suggestions_show_three_after_swipe_commit(self):
        self._commit_swipe_word()
        overlay = self.gesture.get_overlay_data()
        texts = [chip.get("text", "") for chip in overlay.get("suggestion_chips", []) if chip.get("text", "")]
        self.assertEqual(len(texts), 3)
        self.assertEqual(texts, ["help", "held", "helm"])

    def test_suggestion_tap_replaces_last_swipe_word(self):
        self._commit_swipe_word()
        overlay = self.gesture.get_overlay_data()
        chips = [c for c in overlay.get("suggestion_chips", []) if c.get("text")]
        self.assertGreaterEqual(len(chips), 1)

        chip = chips[0]
        cx = chip["x"] + (chip["w"] / 2.0)
        cy = chip["y"] + (chip["h"] / 2.0)

        self.gesture.update(
            _make_hands_data(
                right_present=True,
                right_pinch=True,
                right_index_x=cx,
                right_index_y=cy,
            )
        )

        self.assertEqual(self.action.typed_text[0], "hello ")
        self.assertEqual(self.action.typed_text[1], "help ")
        self.assertEqual(self.action.tapped, ["backspace"] * len("hello "))

    def test_debug_hud_fields_are_minimal(self):
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False))
        hud = self.gesture.get_overlay_data().get("debug_hud", {})
        self.assertEqual(set(hud.keys()), {"pinch_value", "lost_frames"})


if __name__ == "__main__":
    unittest.main()
