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
from backend.gesture_remap.rule_recognizers import RuleLeftClickGesture, RuleMoveMouseGesture
from backend.gestures.switch_mode.HotkeyModeEntryGesture import HotkeyModeEntryGesture
from backend.gestures.mouse_mode.LeftClickGesture import LeftClickGesture
from backend.gestures.mouse_mode.MoveMouseGesture import MoveMouseGesture


class _ActionStub:
    def __init__(self):
        self.left_clicks = []
        self.moves = []

    def left_click(self, x, y):
        self.left_clicks.append((x, y))

    def move_cursor(self, x, y):
        self.moves.append((x, y))


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


def _hands() -> HandsData:
    wrist = {"Right": np.zeros((21, 3), dtype=np.float32)}
    camera = {"Right": np.zeros((21, 3), dtype=np.float32)}
    wrist["Right"][4] = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    wrist["Right"][12] = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    camera["Right"][8] = np.array([0.5, 0.5, 0.0], dtype=np.float32)
    camera["Right"][12] = np.array([0.5, 0.55, 0.0], dtype=np.float32)
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


if __name__ == "__main__":
    unittest.main()
