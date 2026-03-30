import tempfile
import unittest
from pathlib import Path

from backend.gesture_remap.builtins import BuiltInGestureRegistry
from backend.gesture_remap.override_store import GestureOverrideStore
from backend.gesture_remap.pose_templates import PoseMatcherConfig, build_default_templates


class GestureOverrideStoreTests(unittest.TestCase):
    def test_round_trip_and_reset(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "gesture_overrides.json"
            store = GestureOverrideStore(path)
            template = BuiltInGestureRegistry.get("mouse_move").default_pose_template

            store.set_override("mouse_move", template, matcher_config=PoseMatcherConfig())
            reloaded = GestureOverrideStore(path)

            self.assertIsNotNone(reloaded.get("mouse_move"))
            self.assertEqual(reloaded.get("mouse_move").gesture_id, "mouse_move")

            reloaded.reset_override("mouse_move")
            self.assertIsNone(reloaded.get("mouse_move"))

    def test_corrupt_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "gesture_overrides.json"
            path.write_text("{not-json", encoding="utf-8")

            store = GestureOverrideStore(path)

            self.assertEqual(store.list_records(), [])

    def test_conflict_detection_blocks_near_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "gesture_overrides.json"
            store = GestureOverrideStore(path)
            registry = BuiltInGestureRegistry
            candidate = registry.get("left_click").saved_pose_template

            other_def, result = store.validate_override(
                registry,
                "right_click",
                candidate,
                PoseMatcherConfig(conflict_threshold=0.30),
            )

            self.assertIsNotNone(other_def)
            self.assertEqual(other_def.id, "left_click")
            self.assertLessEqual(result.score, 0.30)


if __name__ == "__main__":
    unittest.main()
