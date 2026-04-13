import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.HandsData import HandsData
from backend.gesture_remap.builtins import BuiltInGestureRegistry
from backend.gesture_remap.override_store import GestureOverrideStore
from backend.gesture_remap.pose_templates import (
    PoseMatcherConfig,
    build_default_templates,
    compare_pose_templates,
)
from backend.gesture_remap.recognizers import TemplateLeftClickGesture
from backend.gesture_remap.rule_overrides import GestureRuleOverride
from backend.gesture_remap.rule_recognizers import (
    RuleLeftClickGesture,
    RuleMoveMouseGesture,
    RuleRightClickGesture,
)
from backend.gestures.GestureUtils import camera_to_screen
from backend.gestures.mouse_mode.RightClickGesture import RightClickGesture
from backend.gestures.switch_mode.HotkeyModeEntryGesture import HotkeyModeEntryGesture
from backend.gestures.mouse_mode.LeftClickGesture import LeftClickGesture
from backend.gestures.mouse_mode.MoveMouseGesture import MoveMouseGesture


class _ActionStub:
    def __init__(self):
        self.left_clicks = []
        self.moves = []
        self.right_clicks = []

    def left_click(self, x, y):
        self.left_clicks.append((x, y))

    def move_cursor(self, x, y):
        self.moves.append((x, y))

    def right_click(self, x, y):
        self.right_clicks.append((x, y))


class _StrategizerStub:
    def __init__(self):
        self.action = _ActionStub()
        self.screen_width = 1920
        self.screen_height = 1080
        self.config = {
            "finger_extension_angle": 155.0,
            "scroll_sensitivity": 100,
            "pinch_threshold": 0.30,
            "mouse_tracking_pending_frames": 1,
            "click_pending_frames": 3,
            "scroll_pending_frames": 2,
            "ending_frames": 2,
            "mouse_move_min_delta_px": 1,
            "mouse_move_cadence_ms": 16,
            "keyboard_mode_entry_pending_frames": 6,
            "keyboard_mode_exit_pending_frames": 5,
            "keyboard_mode_exit_extension_angle": 150.0,
            "keyboard_mode_exit_max_openness": 0.16,
            "keyboard_mode_exit_max_extension_ratio": 0.90,
            "keyboard_mode_exit_max_avg_finger_angle": 145.0,
        }


class _CursorFollowingActionStub(_ActionStub):
    def left_click(self, x=None, y=None):
        self.left_clicks.append((x, y))

    def right_click(self, x=None, y=None):
        self.right_clicks.append((x, y))

    def cursor_move_smoothing_enabled(self):
        return True


def _hands(index_x: float = 0.5, index_y: float = 0.5) -> HandsData:
    wrist = {"Right": np.zeros((21, 3), dtype=np.float32)}
    camera = {"Right": np.zeros((21, 3), dtype=np.float32)}
    wrist["Right"][4] = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    wrist["Right"][12] = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    camera["Right"][8] = np.array([index_x, index_y, 0.0], dtype=np.float32)
    camera["Right"][12] = np.array([index_x, index_y + 0.05, 0.0], dtype=np.float32)
    return HandsData(wrist, camera)


class GesturePoseMatchingTests(unittest.TestCase):
    def test_exact_template_matches_and_different_pose_does_not(self):
        templates = build_default_templates()
        config = PoseMatcherConfig(enter_threshold=0.24)

        exact = compare_pose_templates(templates["mouse_move"], templates["mouse_move"], config)
        different = compare_pose_templates(templates["mouse_move"], templates["switch_to_mouse"], config)

        self.assertTrue(exact.matched)
        self.assertLess(exact.score, config.enter_threshold)
        self.assertFalse(different.matched)
        self.assertGreater(different.score, config.enter_threshold)

    def test_registry_uses_default_without_override(self):
        strategizer = _StrategizerStub()
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = GestureOverrideStore(Path(tmp_dir) / "gesture_overrides.json")

            recognizer = BuiltInGestureRegistry.build_runtime_gesture("left_click", strategizer, store)

            self.assertIsInstance(recognizer, LeftClickGesture)
            self.assertNotIsInstance(recognizer, TemplateLeftClickGesture)

    def test_registry_builds_hotkey_switch_gesture(self):
        strategizer = _StrategizerStub()
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = GestureOverrideStore(Path(tmp_dir) / "gesture_overrides.json")

            recognizer = BuiltInGestureRegistry.build_runtime_gesture("switch_to_hotkey", strategizer, store)

            self.assertIsInstance(recognizer, HotkeyModeEntryGesture)

    def test_registry_uses_template_override_when_present(self):
        strategizer = _StrategizerStub()
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = GestureOverrideStore(Path(tmp_dir) / "gesture_overrides.json")
            template = BuiltInGestureRegistry.get("left_click").default_pose_template
            store.set_override("left_click", template, matcher_config=PoseMatcherConfig())

            recognizer = BuiltInGestureRegistry.build_runtime_gesture("left_click", strategizer, store)

            self.assertIsInstance(recognizer, TemplateLeftClickGesture)

    def test_registry_uses_rule_override_when_present(self):
        strategizer = _StrategizerStub()
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = GestureOverrideStore(Path(tmp_dir) / "gesture_overrides.json")
            store.set_rule_override(
                "left_click",
                GestureRuleOverride(
                    conditions=[{"op": "hand_exists", "hand": "dominant"}],
                    pending_frames=3,
                    ending_frames=2,
                ),
            )

            recognizer = BuiltInGestureRegistry.build_runtime_gesture("left_click", strategizer, store)

            self.assertIsInstance(recognizer, RuleLeftClickGesture)

    def test_rule_snapshot_override_replaces_default_detection(self):
        strategizer = _StrategizerStub()
        hands_data = _hands()

        default_recognizer = LeftClickGesture(
            strategizer.action,
            strategizer.screen_width,
            strategizer.screen_height,
            priority=10,
            pinch_threshold=0.30,
            extension_threshold=155.0,
            pending_frames=3,
            ending_frames=2,
        )
        detected_default, _ = default_recognizer.detect_gesture(hands_data)
        self.assertFalse(detected_default)

        rule_recognizer = RuleLeftClickGesture(
            strategizer.action,
            strategizer.screen_width,
            strategizer.screen_height,
            priority=10,
            pinch_threshold=0.30,
            extension_threshold=155.0,
            pending_frames=3,
            ending_frames=2,
            rule_override=GestureRuleOverride(
                conditions=[{"op": "hand_exists", "hand": "dominant"}],
                pending_frames=3,
                ending_frames=2,
            ),
        )
        detected_rule, data = rule_recognizer.detect_gesture(hands_data)

        self.assertTrue(detected_rule)
        self.assertIsNotNone(data)
        rule_recognizer.execute_single_click(data)
        self.assertEqual(len(strategizer.action.left_clicks), 1)

    def test_rule_continuous_override_replaces_default_detection(self):
        strategizer = _StrategizerStub()
        hands_data = _hands()

        default_recognizer = MoveMouseGesture(
            strategizer.action,
            strategizer.screen_width,
            strategizer.screen_height,
            priority=1,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=2,
        )
        detected_default, _ = default_recognizer.detect_gesture(hands_data)
        self.assertFalse(detected_default)

        rule_recognizer = RuleMoveMouseGesture(
            strategizer.action,
            strategizer.screen_width,
            strategizer.screen_height,
            priority=1,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=2,
            min_delta_px=0,
            cadence_ms=1,
            rule_override=GestureRuleOverride(
                conditions=[{"op": "hand_exists", "hand": "dominant"}],
                pending_frames=1,
                ending_frames=2,
            ),
        )
        detected_rule, data = rule_recognizer.detect_gesture(hands_data)

        self.assertTrue(detected_rule)
        self.assertIsNotNone(data)
        rule_recognizer.execute_action(data)
        self.assertEqual(len(strategizer.action.moves), 1)

    def test_screen_interaction_sensitivity_applies_to_mouse_coordinate_recognizers(self):
        strategizer = _StrategizerStub()
        hands_data = _hands(index_x=0.40, index_y=0.60)
        expected_position = camera_to_screen(
            hands_data.camera.dominant.index.tip,
            strategizer.screen_width,
            strategizer.screen_height,
            sensitivity=2.0,
        )

        rule_move = RuleMoveMouseGesture(
            strategizer.action,
            strategizer.screen_width,
            strategizer.screen_height,
            priority=1,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=2,
            min_delta_px=0,
            cadence_ms=1,
            screen_interaction_sensitivity=2.0,
            rule_override=GestureRuleOverride(
                conditions=[{"op": "hand_exists", "hand": "dominant"}],
                pending_frames=1,
                ending_frames=2,
            ),
        )
        template_left_click = TemplateLeftClickGesture(
            strategizer.action,
            strategizer.screen_width,
            strategizer.screen_height,
            priority=10,
            pinch_threshold=0.30,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=2,
            screen_interaction_sensitivity=2.0,
            pose_template=build_default_templates()["left_click"],
            matcher_config=PoseMatcherConfig(),
        )
        template_left_click._matches_pose = lambda current_hands: True
        rule_right_click = RuleRightClickGesture(
            strategizer.action,
            strategizer.screen_width,
            strategizer.screen_height,
            priority=10,
            pinch_threshold=0.30,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=2,
            screen_interaction_sensitivity=2.0,
            rule_override=GestureRuleOverride(
                conditions=[{"op": "hand_exists", "hand": "dominant"}],
                pending_frames=1,
                ending_frames=2,
            ),
        )

        detected_move, move_data = rule_move.detect_gesture(hands_data)
        detected_left, left_click_data = template_left_click.detect_gesture(hands_data)
        detected_right, right_click_data = rule_right_click.detect_gesture(hands_data)

        self.assertTrue(detected_move)
        self.assertTrue(detected_left)
        self.assertTrue(detected_right)
        self.assertEqual(move_data, expected_position)
        self.assertEqual(left_click_data, expected_position)
        self.assertEqual(right_click_data, expected_position)

        rule_move.execute_action(move_data)
        template_left_click.execute_single_click(left_click_data)
        rule_right_click.execute_action(right_click_data)

        self.assertEqual(strategizer.action.moves, [expected_position])
        self.assertEqual(strategizer.action.left_clicks, [expected_position])
        self.assertEqual(strategizer.action.right_clicks, [expected_position])

    def test_click_gestures_follow_current_cursor_when_pointer_smoothing_is_enabled(self):
        action = _CursorFollowingActionStub()

        left_click = LeftClickGesture(
            action,
            screen_width=1920,
            screen_height=1080,
            priority=10,
            pinch_threshold=0.30,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=2,
        )
        right_click = RightClickGesture(
            action,
            screen_width=1920,
            screen_height=1080,
            priority=10,
            pinch_threshold=0.30,
            extension_threshold=155.0,
            pending_frames=1,
            ending_frames=2,
        )

        left_click.execute_single_click((100, 200))
        right_click.execute_action((300, 400))

        self.assertEqual(action.left_clicks, [(None, None)])
        self.assertEqual(action.right_clicks, [(None, None)])


if __name__ == "__main__":
    unittest.main()
