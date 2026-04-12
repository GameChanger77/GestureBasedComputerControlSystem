import json
import tempfile
import unittest
from pathlib import Path

from backend.gesture_remap.builtins import BuiltInGestureRegistry
from backend.gesture_remap.override_store import GestureOverrideStore
from backend.gesture_remap.pose_templates import PoseMatcherConfig
from backend.gesture_remap.rule_overrides import GestureRuleOverride


class GestureOverrideStoreTests(unittest.TestCase):
    def test_legacy_only_fingers_extended_json_alias_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported rule condition op 'only_fingers_extended.json'"):
            GestureRuleOverride.from_dict(
                {
                    "conditions": [
                        {
                            "op": "only_fingers_extended.json",
                            "fingers": ["index"],
                            "threshold_deg": 155.0,
                        }
                    ],
                    "confirm": {"pending_frames": 3, "ending_frames": 2},
                }
            )

    def test_point_override_round_trip_and_reset(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "gesture_overrides.json"
            store = GestureOverrideStore(path)
            template = BuiltInGestureRegistry.get("mouse_move").default_pose_template

            store.set_override("mouse_move", template, matcher_config=PoseMatcherConfig())
            reloaded = GestureOverrideStore(path)

            record = reloaded.get("mouse_move")
            self.assertIsNotNone(record)
            self.assertTrue(record.is_point_override)
            self.assertEqual(record.gesture_id, "mouse_move")

            reloaded.reset_override("mouse_move")
            self.assertIsNone(reloaded.get("mouse_move"))

    def test_rule_override_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "gesture_overrides.json"
            store = GestureOverrideStore(path)
            rule_override = GestureRuleOverride(
                conditions=[{"op": "hand_exists", "hand": "dominant"}],
                pending_frames=4,
                ending_frames=3,
            )

            store.set_rule_override("left_click", rule_override)
            reloaded = GestureOverrideStore(path)

            record = reloaded.get("left_click")
            self.assertIsNotNone(record)
            self.assertTrue(record.is_rule_override)
            self.assertEqual(record.rule_override.pending_frames, 4)
            self.assertEqual(record.rule_override.ending_frames, 3)
            self.assertEqual(record.rule_override.conditions[0]["op"], "hand_exists")

    def test_backward_compatible_point_payload_loads_without_override_kind(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "gesture_overrides.json"
            template = BuiltInGestureRegistry.get("mouse_move").default_pose_template
            payload = {
                "version": 1,
                "overrides": {
                    "mouse_move": {
                        "gesture_id": "mouse_move",
                        "enabled": True,
                        "pose_template": template.to_dict(),
                        "matcher_config": PoseMatcherConfig().to_dict(),
                        "updated_at": "2026-04-01T00:00:00+00:00",
                    }
                },
            }
            path.write_text(json.dumps(payload), encoding="utf-8")

            store = GestureOverrideStore(path)

            record = store.get("mouse_move")
            self.assertIsNotNone(record)
            self.assertTrue(record.is_point_override)
            self.assertIsNotNone(record.pose_template)

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

    def test_builtin_rule_defaults_use_canonical_only_fingers_extended_op(self):
        config_source = {
            "finger_extension_angle": 155.0,
            "mouse_tracking_pending_frames": 1,
            "scroll_pending_frames": 2,
            "ending_frames": 2,
        }

        mouse_move_rule = BuiltInGestureRegistry.get("mouse_move").build_default_rule_override(config_source)
        scroll_rule = BuiltInGestureRegistry.get("scroll").build_default_rule_override(config_source)

        self.assertEqual(mouse_move_rule.conditions[0]["op"], "only_fingers_extended")
        self.assertEqual(scroll_rule.conditions[0]["op"], "only_fingers_extended")


if __name__ == "__main__":
    unittest.main()
