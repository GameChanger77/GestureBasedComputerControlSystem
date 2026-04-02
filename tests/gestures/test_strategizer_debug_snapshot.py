import unittest
from pathlib import Path
import tempfile
from contextlib import ExitStack
from unittest.mock import patch

import numpy as np

from backend.HandsData import HandsData
from backend.Strategizer import Strategizer, ControlMode


class _ActionStub:
    def move_cursor(self, *_args, **_kwargs):
        pass

    def left_click(self, *_args, **_kwargs):
        pass

    def right_click(self, *_args, **_kwargs):
        pass

    def scroll(self, *_args, **_kwargs):
        pass

    def press_key(self, *_args, **_kwargs):
        pass

    def release_key(self, *_args, **_kwargs):
        pass

    def type_text(self, *_args, **_kwargs):
        pass

    def release_all_keys(self):
        pass

    def set_pending_latency_origin_ts_ns(self, _ts):
        pass

    def get_runtime_debug_snapshot(self):
        return {
            "cursor": {"local_x": 10, "local_y": 20, "global_x": 10, "global_y": 20},
            "latest_action_event": {"type": "cursor_move", "global_x": 10, "global_y": 20},
        }


class _ConfigStub(dict):
    def __init__(self, config_path: Path):
        super().__init__(
            keyboard_layout="qwerty",
            keyboard_theme="dark",
            finger_extension_angle=155.0,
            scroll_sensitivity=100,
            pinch_threshold=0.30,
            left_click_hold_time_sec=1.0,
            mouse_tracking_pending_frames=1,
            click_pending_frames=1,
            scroll_pending_frames=1,
            ending_frames=1,
            keyboard_mode_entry_pending_frames=1,
            keyboard_mode_exit_pending_frames=1,
            keyboard_mode_exit_extension_angle=150.0,
            keyboard_mode_exit_max_openness=0.16,
            keyboard_mode_exit_max_extension_ratio=0.90,
            keyboard_mode_exit_max_avg_finger_angle=145.0,
            keyboard_mode_switch_cooldown_sec=0.0,
            screen_safe_margin=50,
            debug_mode=False,
        )
        self.config_path = config_path
        self.config = self


def _right_hand_hands() -> HandsData:
    wrist = {"Right": np.zeros((21, 3), dtype=np.float32)}
    camera = {"Right": np.zeros((21, 3), dtype=np.float32)}
    return HandsData(wrist, camera)


def _extension_side_effect():
    sequence = [False, True, False, False, False]
    index = {"value": 0}

    def _impl(*_args, **_kwargs):
        value = sequence[index["value"] % len(sequence)]
        index["value"] += 1
        return value

    return _impl


def _pinch_side_effect(active_slot: int):
    sequence = [False, False, False, False]
    sequence[active_slot] = True
    index = {"value": 0}

    def _impl(*_args, **_kwargs):
        value = sequence[index["value"] % len(sequence)]
        index["value"] += 1
        return value

    return _impl


class StrategizerDebugSnapshotTests(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.config = _ConfigStub(Path(self._tmp_dir.name) / "gesture_config.json")
        self.strategizer = Strategizer(_ActionStub(), self.config, 1920, 1080)
        self.strategizer.mouse_mode_gestures = [
            gesture
            for gesture in self.strategizer.mouse_mode_gestures
            if getattr(gesture, "debug_name", "") in {"Mouse Move", "Left Click", "Right Click", "Scroll"}
        ]
        self.strategizer._rebuild_sorted_gestures(self.strategizer.current_mode)

    def tearDown(self):
        self._tmp_dir.cleanup()

    def test_snapshot_contains_hand_state_and_winning_action(self):
        hands = _right_hand_hands()
        move_gesture = next(
            gesture for gesture in self.strategizer.mouse_mode_gestures if getattr(gesture, "debug_name", "") == "Mouse Move"
        )
        other_gestures = [
            gesture
            for gesture in self.strategizer.mouse_mode_gestures
            if gesture is not move_gesture
        ]

        with ExitStack() as stack:
            stack.enter_context(patch("backend.Strategizer.is_finger_extended", side_effect=_extension_side_effect()))
            stack.enter_context(patch("backend.Strategizer.are_fingers_pinched", side_effect=_pinch_side_effect(1)))
            stack.enter_context(
                patch.object(move_gesture, "detect_gesture", side_effect=[(True, (100, 100)), (True, (120, 140))])
            )
            for gesture in other_gestures:
                stack.enter_context(patch.object(gesture, "detect_gesture", return_value=(False, None)))
            self.strategizer.strategize(hands)
            self.strategizer.strategize(hands)

        snapshot = self.strategizer.get_debug_snapshot()
        self.assertEqual(snapshot["mode"], "MOUSE")
        self.assertIn("hands", snapshot)
        self.assertIn("mode_candidates", snapshot)
        self.assertIn("winning_action", snapshot)
        self.assertIn("action_debug", snapshot)

        right_hand = next(entry for entry in snapshot["hands"] if entry["side"] == "Right")
        self.assertTrue(right_hand["present"])
        self.assertEqual(right_hand["extended_fingers"], ["Index"])
        self.assertEqual(right_hand["detected_pinches"], ["Thumb + Middle"])

        winning = snapshot["winning_action"]
        self.assertIsNotNone(winning)
        self.assertEqual(winning["name"], "Mouse Move")
        self.assertEqual(snapshot["action_debug"]["cursor"]["global_x"], 10)

    def test_snapshot_marks_lower_priority_gesture_as_suppressed(self):
        hands = _right_hand_hands()
        right_click = next(
            gesture for gesture in self.strategizer.mouse_mode_gestures if getattr(gesture, "debug_name", "") == "Right Click"
        )
        move_gesture = next(
            gesture for gesture in self.strategizer.mouse_mode_gestures if getattr(gesture, "debug_name", "") == "Mouse Move"
        )
        other_gestures = [
            gesture
            for gesture in self.strategizer.mouse_mode_gestures
            if gesture not in {right_click, move_gesture}
        ]

        with ExitStack() as stack:
            stack.enter_context(patch("backend.Strategizer.is_finger_extended", side_effect=_extension_side_effect()))
            stack.enter_context(patch("backend.Strategizer.are_fingers_pinched", side_effect=_pinch_side_effect(2)))
            stack.enter_context(
                patch.object(right_click, "detect_gesture", side_effect=[(True, (100, 100)), (True, (100, 100))])
            )
            stack.enter_context(
                patch.object(move_gesture, "detect_gesture", side_effect=[(True, (10, 10)), (True, (10, 10))])
            )
            for gesture in other_gestures:
                stack.enter_context(patch.object(gesture, "detect_gesture", return_value=(False, None)))
            self.strategizer.strategize(hands)
            self.strategizer.strategize(hands)

        snapshot = self.strategizer.get_debug_snapshot()
        mode_entries = {entry["name"]: entry for entry in snapshot["mode_candidates"]}
        self.assertEqual(snapshot["winning_action"]["name"], "Right Click")
        self.assertTrue(mode_entries["Right Click"]["executed"])
        self.assertTrue(mode_entries["Mouse Move"]["suppressed"])
        self.assertEqual(mode_entries["Mouse Move"]["state"], "suppressed")

    def test_keyboard_exit_switch_is_blocked_while_key_selection_pinch_is_latched(self):
        hands = _right_hand_hands()
        self.strategizer.set_mode(ControlMode.KEYBOARD)
        air_typing = next(gesture for gesture in self.strategizer.keyboard_mode_gestures if getattr(gesture, "debug_name", "") == "Air Typing")
        air_typing._special_key_pinch_latched = True

        exit_gesture = next(
            gesture for gesture in self.strategizer.switch_mode_gestures if getattr(gesture, "debug_gesture_id", "") == "switch_to_mouse"
        )

        with patch.object(exit_gesture, "update", return_value=True) as exit_update:
            self.strategizer.strategize(hands)

        self.assertFalse(exit_update.called)
        self.assertEqual(self.strategizer.current_mode, ControlMode.KEYBOARD)
        switch_entries = {
            entry["name"]: entry for entry in self.strategizer.get_debug_snapshot()["mode_switch_candidates"]
        }
        self.assertTrue(switch_entries["Switch To Mouse Mode"]["suppressed"])
        self.assertIn("Key selection pinch is still latched", switch_entries["Switch To Mouse Mode"]["note"])


if __name__ == "__main__":
    unittest.main()
