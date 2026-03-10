import unittest

import numpy as np

from backend.HandsData import HandsData
from backend.gestures.keyboard_mode.AirTypingGesture import AirTypingGesture


class _FakeAction:
    def __init__(self):
        self.tapped = []
        self.key_down_events = []
        self.key_up_events = []
        self.hotkeys = []
        self.typed_text = []

    def tap_key(self, key_code):
        self.tapped.append(key_code)

    def key_down(self, key_code):
        self.key_down_events.append(key_code)

    def key_up(self, key_code):
        self.key_up_events.append(key_code)

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

    arr[1] = wrist + np.array([-0.03, -0.02, 0.0], dtype=np.float32)
    arr[2] = wrist + np.array([-0.04, -0.04, 0.0], dtype=np.float32)
    arr[3] = wrist + np.array([-0.05, -0.06, 0.0], dtype=np.float32)
    arr[4] = wrist + np.array([-0.06, -0.08, 0.0], dtype=np.float32)

    arr[5] = wrist + np.array([-0.01, -0.02, 0.0], dtype=np.float32)
    arr[6] = wrist + np.array([0.00, -0.06, 0.0], dtype=np.float32)
    arr[7] = wrist + np.array([0.01, -0.10, 0.0], dtype=np.float32)
    arr[8] = np.array([index_x, index_y, 0.0], dtype=np.float32)

    arr[9] = wrist + np.array([0.01, -0.02, 0.0], dtype=np.float32)
    arr[10] = wrist + np.array([0.02, -0.06, 0.0], dtype=np.float32)
    arr[11] = wrist + np.array([0.03, -0.10, 0.0], dtype=np.float32)
    arr[12] = wrist + np.array([0.04, -0.13, 0.0], dtype=np.float32)

    arr[13] = wrist + np.array([0.03, -0.01, 0.0], dtype=np.float32)
    arr[14] = wrist + np.array([0.04, -0.05, 0.0], dtype=np.float32)
    arr[15] = wrist + np.array([0.05, -0.08, 0.0], dtype=np.float32)
    arr[16] = wrist + np.array([0.06, -0.11, 0.0], dtype=np.float32)

    arr[17] = wrist + np.array([0.05, 0.00, 0.0], dtype=np.float32)
    arr[18] = wrist + np.array([0.06, -0.03, 0.0], dtype=np.float32)
    arr[19] = wrist + np.array([0.07, -0.06, 0.0], dtype=np.float32)
    arr[20] = wrist + np.array([0.08, -0.09, 0.0], dtype=np.float32)
    return arr


def _make_wrist_hand(pinch: bool) -> np.ndarray:
    arr = np.zeros((21, 3), dtype=np.float32)
    arr[0] = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    arr[4] = np.array([0.02, 0.0, 0.0], dtype=np.float32)   # thumb tip
    arr[12] = np.array([0.03 if pinch else 0.70, 0.0, 0.0], dtype=np.float32)  # middle tip
    return arr


def _make_hands_data(
    *,
    right_present: bool = True,
    left_present: bool = False,
    right_pinch: bool = False,
    left_pinch: bool = False,
    right_index_x: float = 0.74,
    right_index_y: float = 0.42,
    left_index_x: float = 0.26,
    left_index_y: float = 0.42,
    right_wrist_x: float = 0.78,
    left_wrist_x: float = 0.22,
) -> HandsData:
    camera = {}
    wrist = {}
    if right_present:
        camera["Right"] = _make_camera_hand(right_wrist_x, right_index_x, right_index_y)
        wrist["Right"] = _make_wrist_hand(right_pinch)
    if left_present:
        camera["Left"] = _make_camera_hand(left_wrist_x, left_index_x, left_index_y)
        wrist["Left"] = _make_wrist_hand(left_pinch)
    return HandsData(wrist, camera)


class AirTypingSwipeStateTests(unittest.TestCase):
    def setUp(self):
        self.action = _FakeAction()
        self.config = {
            "keyboard_swipe_min_points": 3,
            "keyboard_swipe_min_unique_keys": 3,
            "keyboard_swipe_decode_top_k": 3,
            "keyboard_swipe_confidence_threshold": 0.45,
            "keyboard_swipe_release_pending_frames": 1,
            "keyboard_swipe_tracking_grace_frames": 2,
            "pinch_threshold": 0.15,
            "keyboard_flip_x_for_mapping": False,
        }
        self.gesture = AirTypingGesture(self.action, config=self.config, priority=15)
        self._clock = 100.0
        self.gesture._now_seconds = lambda: self._clock
        # Hardcoded resume_stability_frames=4 in gesture; warm up once for deterministic tests.
        for _ in range(4):
            self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.74))

        # Deterministic decoder behavior for integration-state tests.
        self.gesture._swipe_decoder.decode = lambda trace, top_k=3: ("hello", 0.90, ["hello", "help"])
        self.gesture._map_tip_to_slot = lambda side, tip, frame: (
            {"id": "h"} if tip[0] < 0.64 else
            {"id": "e"} if tip[0] < 0.68 else
            {"id": "l"} if tip[0] < 0.74 else
            {"id": "o"}
        )

    def _advance_time(self, dt: float = 0.05):
        self._clock += dt

    def test_right_pinch_start_hold_release_commits_word(self):
        x_positions = [0.62, 0.66, 0.70, 0.76]
        for x in x_positions:
            data = _make_hands_data(right_present=True, right_pinch=True, right_index_x=x)
            self.gesture.update(data)
            self._advance_time()

        release_data = _make_hands_data(right_present=True, right_pinch=False, right_index_x=0.78)
        self.gesture.update(release_data)
        self._advance_time()

        self.assertEqual(self.action.typed_text, ["hello "])

    def test_left_pinch_is_ignored_for_swipe(self):
        for _ in range(4):
            data = _make_hands_data(
                right_present=True,
                left_present=True,
                right_pinch=False,
                left_pinch=True,
                right_index_x=0.70,
                left_index_x=0.20,
            )
            self.gesture.update(data)
            self._advance_time()

        self.assertEqual(self.action.tapped, [])
        self.assertFalse(self.gesture._swipe_active)

    def test_right_hand_loss_cancels_active_swipe_after_grace(self):
        start = _make_hands_data(right_present=True, right_pinch=True, right_index_x=0.66)
        self.gesture.update(start)
        self._advance_time()
        self.assertTrue(self.gesture._swipe_active)

        lost = _make_hands_data(right_present=False, left_present=False)
        self.gesture.update(lost)
        self._advance_time()
        self.assertTrue(self.gesture._swipe_active)
        self.gesture.update(lost)
        self._advance_time()
        self.assertTrue(self.gesture._swipe_active)
        self.gesture.update(lost)
        self._advance_time()

        self.assertFalse(self.gesture._swipe_active)
        self.assertEqual(self.action.tapped, [])

    def test_right_hand_loss_within_grace_resumes_swipe(self):
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.62))
        self._advance_time()
        lost = _make_hands_data(right_present=False, left_present=False)
        self.gesture.update(lost)
        self._advance_time()
        self.assertTrue(self.gesture._swipe_active)
        self.assertEqual(self.gesture._swipe_lost_frames, 1)

        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.66))
        self._advance_time()
        self.assertTrue(self.gesture._swipe_active)
        self.assertEqual(self.gesture._swipe_lost_frames, 0)

    def test_no_pinch_no_commit(self):
        for x in [0.62, 0.66, 0.70, 0.74, 0.78]:
            data = _make_hands_data(right_present=True, right_pinch=False, right_index_x=x)
            self.gesture.update(data)
            self._advance_time()

        self.assertEqual(self.action.tapped, [])
        self.assertFalse(self.gesture._swipe_active)

    def test_single_key_pinch_release_taps_key(self):
        for x in [0.60, 0.61, 0.62]:
            data = _make_hands_data(right_present=True, right_pinch=True, right_index_x=x)
            self.gesture.update(data)
            self._advance_time()

        release_data = _make_hands_data(right_present=True, right_pinch=False, right_index_x=0.62)
        self.gesture.update(release_data)
        self._advance_time()

        self.assertEqual(self.action.tapped, ["h"])
        self.assertFalse(self.gesture._swipe_active)

    def test_release_outside_keyboard_cancels_swipe_commit(self):
        self.gesture._map_tip_to_slot = lambda side, tip, frame: (
            {"id": "h"} if tip[0] < 0.64 else
            {"id": "e"} if tip[0] < 0.68 else
            {"id": "l"} if tip[0] < 0.74 else
            None
        )

        for x in [0.62, 0.66, 0.70]:
            self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=x))
            self._advance_time()
        # Release outside all keys.
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.90))
        self._advance_time()

        self.assertEqual(self.action.typed_text, [])
        self.assertEqual(self.action.tapped, [])

    def test_special_key_pinch_taps_immediately_and_latches_until_release(self):
        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "backspace"}

        start = _make_hands_data(right_present=True, right_pinch=True, right_index_x=0.80)
        self.gesture.update(start)
        self._advance_time()
        self.assertEqual(self.action.tapped, ["backspace"])
        self.assertFalse(self.gesture._swipe_active)

        hold = _make_hands_data(right_present=True, right_pinch=True, right_index_x=0.80)
        self.gesture.update(hold)
        self._advance_time()
        self.assertEqual(self.action.tapped, ["backspace"])
        self.assertFalse(self.gesture._swipe_active)

        release = _make_hands_data(right_present=True, right_pinch=False, right_index_x=0.80)
        self.gesture.update(release)
        self._advance_time()
        repinch = _make_hands_data(right_present=True, right_pinch=True, right_index_x=0.80)
        self.gesture.update(repinch)
        self._advance_time()
        self.assertEqual(self.action.tapped, ["backspace", "backspace"])

    def test_modifier_key_pinch_toggles_sticky_modifier(self):
        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "left_shift"}

        pinch = _make_hands_data(right_present=True, right_pinch=True, right_index_x=0.40)
        self.gesture.update(pinch)
        self._advance_time()

        self.assertEqual(self.action.tapped, [])
        self.assertEqual(self.gesture._active_modifiers, {"shift"})
        self.assertFalse(self.gesture._swipe_active)

    def test_fn_modifier_maps_number_row_to_function_key(self):
        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "fn"}
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.40))
        self._advance_time()
        self.assertEqual(self.gesture._active_modifiers, {"fn"})

        # Release to clear special-key latch, then press "1".
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.40))
        self._advance_time()
        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "1"}
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.60))
        self._advance_time()

        self.assertEqual(self.action.tapped, ["f1"])
        self.assertEqual(self.gesture._active_modifiers, set())

    def test_ctrl_plus_fn_plus_number_emits_ctrl_function_hotkey(self):
        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "left_ctrl"}
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.45))
        self._advance_time()
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.45))
        self._advance_time()

        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "fn"}
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.50))
        self._advance_time()
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.50))
        self._advance_time()

        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "1"}
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.60))
        self._advance_time()

        self.assertEqual(self.action.hotkeys, [["left_ctrl", "f1"]])
        self.assertEqual(self.gesture._active_modifiers, set())

    def test_fn_active_relabels_number_row_to_function_keys_in_overlay(self):
        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "fn"}
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.50))
        self._advance_time()

        overlay = self.gesture.get_overlay_data()
        labels = {k["id"]: k.get("label", "") for k in overlay.get("keys", [])}
        self.assertEqual(labels.get("1"), "F1")
        self.assertEqual(labels.get("0"), "F10")
        self.assertEqual(labels.get("minus"), "F11")
        self.assertEqual(labels.get("equals"), "F12")

    def test_caps_lock_pinch_toggles_caps_state(self):
        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "caps_lock"}

        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.5))
        self._advance_time()
        self.assertEqual(self.action.tapped, [])
        self.assertTrue(self.gesture._caps_lock_active)
        self.assertIn("caps_lock", self.gesture.get_overlay_data().get("pressed_keys", []))

        # Release and pinch again to toggle off.
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.5))
        self._advance_time()
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.5))
        self._advance_time()
        self.assertEqual(self.action.tapped, [])
        self.assertFalse(self.gesture._caps_lock_active)
        self.assertNotIn("caps_lock", self.gesture.get_overlay_data().get("pressed_keys", []))

    def test_caps_lock_uppercases_letters_without_os_caps(self):
        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "caps_lock"}
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.5))
        self._advance_time()
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.5))
        self._advance_time()

        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "a"}
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.5))
        self._advance_time()
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.5))
        self._advance_time()

        self.assertEqual(self.action.hotkeys, [["left_shift", "a"]])

    def test_caps_lock_does_not_block_swipe_and_uppercases_word(self):
        self.gesture._caps_lock_active = True
        self.gesture._map_tip_to_slot = lambda side, tip, frame: (
            {"id": "h"} if tip[0] < 0.64 else
            {"id": "e"} if tip[0] < 0.68 else
            {"id": "l"} if tip[0] < 0.74 else
            {"id": "o"}
        )

        for x in [0.62, 0.66, 0.70, 0.76]:
            self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=x))
            self._advance_time()
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.76))
        self._advance_time()

        self.assertEqual(self.action.typed_text, ["HELLO "])

    def test_post_commit_flick_left_replaces_with_alt_1(self):
        for x in [0.62, 0.66, 0.70, 0.76]:
            self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=x))
            self._advance_time()
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.76))
        self._advance_time()
        self.assertTrue(self.gesture._flick_window_active)

        for x in [0.76, 0.67, 0.58]:
            self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=x))
            self._advance_time()

        self.assertEqual(self.action.typed_text, ["hello ", "help "])
        self.assertEqual(self.action.tapped, ["backspace"] * len("hello "))
        self.assertFalse(self.gesture._flick_window_active)

    def test_post_commit_flick_up_replaces_with_alt_2(self):
        self.gesture._swipe_decoder.decode = lambda trace, top_k=3: ("hello", 0.90, ["hello", "help", "held", "helm"])
        for x in [0.62, 0.66, 0.70, 0.76]:
            self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=x, right_index_y=0.48))
            self._advance_time()
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.76, right_index_y=0.48))
        self._advance_time()
        self.assertTrue(self.gesture._flick_window_active)

        for y in [0.48, 0.40, 0.31]:
            self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.76, right_index_y=y))
            self._advance_time()

        self.assertEqual(self.action.typed_text, ["hello ", "held "])
        self.assertFalse(self.gesture._flick_window_active)

    def test_post_commit_flick_window_expires_without_replacement(self):
        for x in [0.62, 0.66, 0.70, 0.76]:
            self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=x))
            self._advance_time()
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.76))
        self.assertTrue(self.gesture._flick_window_active)
        self.assertEqual(self.action.typed_text, ["hello "])

        self._advance_time(3.1)
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.76))
        self.assertFalse(self.gesture._flick_window_active)
        self.assertEqual(self.action.typed_text, ["hello "])

    def test_pinch_during_flick_window_cancels_window_and_starts_next_swipe(self):
        for x in [0.62, 0.66, 0.70, 0.76]:
            self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=x))
            self._advance_time()
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.76))
        self._advance_time()
        self.assertTrue(self.gesture._flick_window_active)

        self.gesture.update(
            _make_hands_data(
                right_present=True,
                right_pinch=True,
                right_index_x=0.62,
                right_index_y=0.60,
            )
        )
        self.assertFalse(self.gesture._flick_window_active)
        self.assertTrue(self.gesture._swipe_active)

    def test_modifiers_stack_and_apply_to_next_key_as_combo(self):
        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "left_win"}
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.5))
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.5))

        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "left_shift"}
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.5))
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.5))

        self.assertEqual(self.gesture._active_modifiers, {"win", "shift"})

        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "s"}
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.5))

        self.assertEqual(self.action.hotkeys, [["left_win", "left_shift", "s"]])
        self.assertEqual(self.gesture._active_modifiers, set())
        self.assertFalse(self.gesture._swipe_active)

    def test_toggling_one_modifier_does_not_clear_others(self):
        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "left_ctrl"}
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.5))
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.5))

        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "left_alt"}
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.5))
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.5))

        self.gesture._map_tip_to_slot = lambda side, tip, frame: {"id": "left_shift"}
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.5))
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.5))
        self.assertEqual(self.gesture._active_modifiers, {"ctrl", "alt", "shift"})

        self.gesture.update(_make_hands_data(right_present=True, right_pinch=True, right_index_x=0.5))
        self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.5))
        self.assertEqual(self.gesture._active_modifiers, {"ctrl", "alt"})

    def test_swipe_points_continue_when_right_hand_crosses_center(self):
        start = _make_hands_data(
            right_present=True,
            right_pinch=True,
            right_index_x=0.78,
            right_wrist_x=0.78,
        )
        self.gesture.update(start)
        points_before = len(self.gesture._swipe_points)
        self.assertGreater(points_before, 0)

        crossed = _make_hands_data(
            right_present=True,
            right_pinch=True,
            right_index_x=0.26,
            right_wrist_x=0.26,
        )
        self.gesture.update(crossed)
        points_after = len(self.gesture._swipe_points)
        self.assertGreater(points_after, points_before)


if __name__ == "__main__":
    unittest.main()
