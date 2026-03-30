import unittest
import tempfile
from pathlib import Path

from backend.gesture_remap.builtins import BuiltInGestureRegistry
from backend.gesture_remap.override_store import GestureOverrideStore
from backend.gesture_remap.pose_templates import (
    PoseMatcherConfig,
    build_default_templates,
    compare_pose_templates,
)
from backend.gesture_remap.recognizers import TemplateLeftClickGesture
from backend.gestures.mouse_mode.LeftClickGesture import LeftClickGesture


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
        class _StrategizerStub:
            def __init__(self):
                self.action = object()
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
                    "mouse_move_min_delta_px": 2,
                    "mouse_move_cadence_ms": 75,
                    "keyboard_mode_entry_pending_frames": 6,
                    "keyboard_mode_exit_pending_frames": 5,
                    "keyboard_mode_exit_extension_angle": 150.0,
                    "keyboard_mode_exit_max_openness": 0.16,
                    "keyboard_mode_exit_max_extension_ratio": 0.90,
                    "keyboard_mode_exit_max_avg_finger_angle": 145.0,
                }

            def __getitem__(self, key):
                return self.config[key]

        strategizer = _StrategizerStub()
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = GestureOverrideStore(Path(tmp_dir) / "gesture_overrides.json")

            recognizer = BuiltInGestureRegistry.build_runtime_gesture("left_click", strategizer, store)

            self.assertIsInstance(recognizer, LeftClickGesture)
            self.assertNotIsInstance(recognizer, TemplateLeftClickGesture)

    def test_registry_uses_template_override_when_present(self):
        class _StrategizerStub:
            def __init__(self):
                self.action = object()
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
                    "mouse_move_min_delta_px": 2,
                    "mouse_move_cadence_ms": 75,
                    "keyboard_mode_entry_pending_frames": 6,
                    "keyboard_mode_exit_pending_frames": 5,
                    "keyboard_mode_exit_extension_angle": 150.0,
                    "keyboard_mode_exit_max_openness": 0.16,
                    "keyboard_mode_exit_max_extension_ratio": 0.90,
                    "keyboard_mode_exit_max_avg_finger_angle": 145.0,
                }

        strategizer = _StrategizerStub()
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = GestureOverrideStore(Path(tmp_dir) / "gesture_overrides.json")
            template = BuiltInGestureRegistry.get("left_click").default_pose_template
            store.set_override("left_click", template, matcher_config=PoseMatcherConfig())

            recognizer = BuiltInGestureRegistry.build_runtime_gesture("left_click", strategizer, store)

            self.assertIsInstance(recognizer, TemplateLeftClickGesture)


if __name__ == "__main__":
    unittest.main()
