import tempfile
import unittest
from pathlib import Path

from backend.gesture_remap.builtins import BuiltInGestureRegistry
from backend.gesture_remap.pose_templates import PoseMatcherConfig, build_pose_template
from backend.gesture_remap.rule_overrides import GestureRuleOverride, POINT_OVERRIDE_KIND, RULE_OVERRIDE_KIND
from backend.macros.macro_models import (
    DOMINANT_TRIGGER_HAND,
    MacroPointTrigger,
    MacroRecord,
    MacroRuleTrigger,
    MacroSwipeConfig,
    RULE_TRIGGER_TYPE_POSE,
    RULE_TRIGGER_TYPE_SWIPE,
)
from backend.macros.macro_store import MacroStore


class MacroStoreTests(unittest.TestCase):
    def test_missing_store_seeds_default_hotkey_macros_once(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "gesture_macros.json"

            store = MacroStore(path, target_os="Windows", seed_defaults=True)

            records = store.list_records()
            self.assertTrue(path.exists())
            self.assertEqual([record.name for record in records], ["Copy", "Paste", "Undo"])
            self.assertEqual([record.shortcut_keys for record in records], [
                ["left_ctrl", "c"],
                ["left_ctrl", "v"],
                ["left_ctrl", "z"],
            ])
            self.assertTrue(all(record.mode == "hotkey" for record in records))
            self.assertTrue(all(record.rule_trigger is not None for record in records))
            self.assertEqual(
                [
                    record.rule_trigger.rule_override.conditions[0]["b"]
                    for record in records
                ],
                ["middle.tip", "ring.tip", "pinky.tip"],
            )

    def test_missing_store_seeds_platform_specific_shortcuts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = MacroStore(Path(tmp_dir) / "gesture_macros.json", target_os="Darwin", seed_defaults=True)

            self.assertEqual(
                [record.shortcut_keys for record in store.list_records()],
                [["left_cmd", "c"], ["left_cmd", "v"], ["left_cmd", "z"]],
            )

    def test_existing_store_is_not_reseeded_when_file_already_exists(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "gesture_macros.json"
            path.write_text('{"version": 2, "macros": {}}', encoding="utf-8")

            store = MacroStore(path, target_os="Windows", seed_defaults=True)

            self.assertEqual(store.list_records(), [])

    def test_rule_macro_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = MacroStore(Path(tmp_dir) / "gesture_macros.json", target_os="Windows")
            record = MacroRecord.build_new(
                name="Rule Macro",
                mode="mouse",
                trigger_kind=RULE_OVERRIDE_KIND,
                point_trigger=None,
                rule_trigger=MacroRuleTrigger(
                    hand="right",
                    trigger_type=RULE_TRIGGER_TYPE_POSE,
                    rule_override=GestureRuleOverride(
                        conditions=[{"op": "hand_count_eq", "value": 1}],
                        pending_frames=1,
                        ending_frames=1,
                    ),
                    start_rule_override=None,
                    swipe_config=None,
                ),
                shortcut_keys=["left_ctrl", "c"],
                target_os="Windows",
            )
            store.upsert(record)

            reloaded = MacroStore(store.path, target_os="Windows")
            loaded = reloaded.get(record.id)
            self.assertIsNotNone(loaded)
            self.assertTrue(loaded.is_rule_trigger)
            self.assertTrue(loaded.rule_trigger.is_pose_trigger)
            self.assertEqual(loaded.rule_trigger.hand, DOMINANT_TRIGGER_HAND)
            self.assertEqual(loaded.shortcut_keys, ["left_ctrl", "c"])

    def test_point_macro_round_trip_and_delete(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = MacroStore(Path(tmp_dir) / "gesture_macros.json", target_os="Linux")
            trigger = MacroPointTrigger(
                hand="either",
                pose_template=build_pose_template(
                    "Macro Trigger",
                    finger_curls={"index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
                    thumb_curl=0.0,
                ),
                editor_pose_template=None,
                matcher_config=PoseMatcherConfig(),
            )
            record = MacroRecord.build_new(
                name="Point Macro",
                mode="keyboard",
                trigger_kind=POINT_OVERRIDE_KIND,
                point_trigger=trigger,
                rule_trigger=None,
                shortcut_keys=["left_ctrl", "left_shift", "s"],
                target_os="Linux",
            )
            store.upsert(record)
            self.assertIsNotNone(store.get(record.id))
            store.delete(record.id)
            self.assertIsNone(store.get(record.id))

    def test_swipe_macro_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = MacroStore(Path(tmp_dir) / "gesture_macros.json", target_os="Darwin")
            record = MacroRecord.build_new(
                name="Swipe Macro",
                mode="hotkey",
                trigger_kind=RULE_OVERRIDE_KIND,
                point_trigger=None,
                rule_trigger=MacroRuleTrigger(
                    hand="left",
                    trigger_type=RULE_TRIGGER_TYPE_SWIPE,
                    rule_override=None,
                    start_rule_override=GestureRuleOverride(
                        conditions=[{"op": "hand_count_eq", "value": 1}],
                        pending_frames=1,
                        ending_frames=1,
                    ),
                    swipe_config=MacroSwipeConfig.from_dict(
                        {
                            "tracked_point": "index.tip",
                            "direction": "left",
                            "min_displacement": 0.16,
                            "min_speed": 0.60,
                            "min_smoothness": 0.70,
                            "start_confirm_frames": 2,
                            "timeout_frames": 20,
                        }
                    ),
                ),
                shortcut_keys=["cmd", "shift", "4"],
                target_os="Darwin",
            )
            store.upsert(record)

            reloaded = MacroStore(store.path, target_os="Darwin")
            loaded = reloaded.get(record.id)
            self.assertIsNotNone(loaded)
            self.assertTrue(loaded.rule_trigger.is_swipe_trigger)
            self.assertEqual(loaded.rule_trigger.hand, DOMINANT_TRIGGER_HAND)
            self.assertEqual(loaded.rule_trigger.swipe_config.direction, "left")
            self.assertEqual(loaded.shortcut_keys, ["left_cmd", "left_shift", "4"])

    def test_legacy_action_steps_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "action_steps"):
            MacroRecord.from_dict(
                {
                    "id": "legacy",
                    "name": "Legacy Macro",
                    "mode": "mouse",
                    "trigger_kind": RULE_OVERRIDE_KIND,
                    "rule_trigger": {
                        "hand": "right",
                        "rule_override": {
                            "conditions": [{"op": "hand_count_eq", "value": 1}],
                            "confirm": {"pending_frames": 1, "ending_frames": 1},
                        },
                    },
                    "action_steps": [{"type": "tap_key", "params": {"key": "a"}}],
                },
                target_os="Windows",
            )

    def test_validate_point_trigger_detects_builtin_conflict(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = MacroStore(Path(tmp_dir) / "gesture_macros.json", target_os="Windows")
            built_in = BuiltInGestureRegistry.get("left_click")
            other_def, comparison = store.validate_point_trigger(
                BuiltInGestureRegistry,
                macro_id=None,
                mode="mouse",
                pose_template=built_in.saved_pose_template,
                matcher_config=PoseMatcherConfig(),
            )
            self.assertEqual(other_def.id, "left_click")
            self.assertLessEqual(comparison.score, PoseMatcherConfig().conflict_threshold)

    def test_validate_point_trigger_detects_other_macro_conflict(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = MacroStore(Path(tmp_dir) / "gesture_macros.json", target_os="Linux")
            template = build_pose_template(
                "Point Macro Trigger",
                finger_curls={"index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
                thumb_curl=0.0,
            )
            existing = MacroRecord.build_new(
                name="Existing Macro",
                mode="keyboard",
                trigger_kind=POINT_OVERRIDE_KIND,
                point_trigger=MacroPointTrigger(
                    hand="left",
                    pose_template=template,
                    editor_pose_template=None,
                    matcher_config=PoseMatcherConfig(),
                ),
                rule_trigger=None,
                shortcut_keys=["left_ctrl", "c"],
                target_os="Linux",
            )
            store.upsert(existing)

            other_record, comparison = store.validate_point_trigger(
                BuiltInGestureRegistry,
                macro_id=None,
                mode="keyboard",
                pose_template=template,
                matcher_config=PoseMatcherConfig(),
            )
            self.assertEqual(other_record.name, "Existing Macro")
            self.assertLessEqual(comparison.score, PoseMatcherConfig().conflict_threshold)


if __name__ == "__main__":
    unittest.main()
