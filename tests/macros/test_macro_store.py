import tempfile
import unittest
from pathlib import Path

from backend.gesture_remap.pose_templates import PoseMatcherConfig, build_pose_template
from backend.gesture_remap.rule_overrides import GestureRuleOverride, POINT_OVERRIDE_KIND, RULE_OVERRIDE_KIND
from backend.macros.macro_models import MacroActionStep, MacroPointTrigger, MacroRecord, MacroRuleTrigger
from backend.macros.macro_store import MacroStore


class MacroStoreTests(unittest.TestCase):
    def test_rule_macro_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = MacroStore(Path(tmp_dir) / "gesture_macros.json")
            record = MacroRecord.build_new(
                name="Rule Macro",
                mode="mouse",
                trigger_kind=RULE_OVERRIDE_KIND,
                point_trigger=None,
                rule_trigger=MacroRuleTrigger(
                    hand="right",
                    rule_override=GestureRuleOverride(
                        conditions=[{"op": "hand_count_eq", "value": 1}],
                        pending_frames=1,
                        ending_frames=1,
                    ),
                ),
                action_steps=[MacroActionStep.from_dict({"type": "left_click", "params": {}})],
            )
            store.upsert(record)

            reloaded = MacroStore(store.path)
            loaded = reloaded.get(record.id)
            self.assertIsNotNone(loaded)
            self.assertTrue(loaded.is_rule_trigger)
            self.assertEqual(loaded.rule_trigger.hand, "right")
            self.assertEqual(loaded.action_steps[0].step_type, "left_click")

    def test_point_macro_round_trip_and_delete(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = MacroStore(Path(tmp_dir) / "gesture_macros.json")
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
                action_steps=[
                    MacroActionStep.from_dict({"type": "tap_hotkey", "params": {"keys": ["left_ctrl", "left_alt", "delete"]}})
                ],
            )
            store.upsert(record)
            self.assertIsNotNone(store.get(record.id))
            store.delete(record.id)
            self.assertIsNone(store.get(record.id))

    def test_all_supported_action_steps_serialize(self):
        steps = [
            {"type": "tap_key", "params": {"key": "a"}},
            {"type": "key_down", "params": {"key": "left_ctrl"}},
            {"type": "key_up", "params": {"key": "left_ctrl"}},
            {"type": "tap_hotkey", "params": {"keys": ["left_ctrl", "left_alt", "delete"]}},
            {"type": "left_click", "params": {}},
            {"type": "right_click", "params": {}},
            {"type": "left_button_down", "params": {}},
            {"type": "left_button_up", "params": {}},
            {"type": "right_button_down", "params": {}},
            {"type": "right_button_up", "params": {}},
            {"type": "scroll", "params": {"delta_x": 0, "delta_y": -240}},
            {"type": "delay_ms", "params": {"duration_ms": 150}},
        ]
        normalized = [MacroActionStep.from_dict(step) for step in steps]
        self.assertEqual([step.step_type for step in normalized], [step["type"] for step in steps])


if __name__ == "__main__":
    unittest.main()
