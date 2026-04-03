import tempfile
import unittest
from pathlib import Path
import json
import subprocess
import sys

import numpy as np

from backend.HandsData import HandsData
from backend.Strategizer import Strategizer, ControlMode
from backend.custom_rules.RuleCompiler import RuleCompiler
from backend.custom_rules.MacroChainRecognizer import MacroChainRecognizer
from backend.gesture_remap.pose_templates import PoseMatcherConfig, build_pose_template
from backend.gesture_remap.rule_overrides import GestureRuleOverride, POINT_OVERRIDE_KIND, RULE_OVERRIDE_KIND
from backend.macros.macro_models import MacroActionStep, MacroPointTrigger, MacroRecord, MacroRuleTrigger
from backend.macros.macro_store import MacroStore


class _MouseStub:
    def __init__(self):
        self.calls = []

    def click(self, button, count):
        self.calls.append(("click", str(button), count))

    def press(self, button):
        self.calls.append(("press", str(button)))

    def release(self, button):
        self.calls.append(("release", str(button)))

    def scroll(self, dx, dy):
        self.calls.append(("scroll", dx, dy))

    @property
    def position(self):
        return (0, 0)

    @position.setter
    def position(self, value):
        self.calls.append(("move", value))


class _KeyboardStub:
    def __init__(self):
        self.calls = []

    def press(self, key):
        self.calls.append(("press", str(key)))

    def release(self, key):
        self.calls.append(("release", str(key)))

    def type(self, text):
        self.calls.append(("type", text))


class _ConfigStub(dict):
    def __init__(self, config_path):
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
            keyboard_mode_switch_cooldown_sec=60.0,
            screen_safe_margin=50,
            debug_mode=False,
        )
        self.config_path = Path(config_path)
        self.config = self


def _hands_for_rule_trigger():
    wrist = {"Right": np.zeros((21, 3), dtype=np.float32)}
    camera = {"Right": np.zeros((21, 3), dtype=np.float32)}
    return HandsData(wrist, camera)


def _hands_for_point_trigger(template):
    wrist = {"Right": template.as_array().copy()}
    camera = {}
    return HandsData(wrist, camera)


class MacroRuntimeTests(unittest.TestCase):
    def test_action_executes_hotkey_and_ordered_steps(self):
        script = """
import json
from backend.Action import Action
from backend.macros.macro_models import MacroActionStep

class MouseStub:
    def click(self, button, count): pass
    def press(self, button): pass
    def release(self, button): pass
    def scroll(self, dx, dy): pass
    @property
    def position(self): return (0, 0)
    @position.setter
    def position(self, value): pass

class KeyboardStub:
    def __init__(self):
        self.calls = []
    def press(self, key):
        self.calls.append(("press", str(key)))
    def release(self, key):
        self.calls.append(("release", str(key)))
    def type(self, text):
        self.calls.append(("type", text))

mouse = MouseStub()
keyboard = KeyboardStub()
action = Action(mouse=mouse, keyboard_test=keyboard, osType="Test")
try:
    action.execute_macro_steps(
        [
            MacroActionStep.from_dict({"type": "key_down", "params": {"key": "left_ctrl"}}),
            MacroActionStep.from_dict({"type": "delay_ms", "params": {"duration_ms": 1}}),
            MacroActionStep.from_dict({"type": "key_up", "params": {"key": "left_ctrl"}}),
            MacroActionStep.from_dict({"type": "tap_hotkey", "params": {"keys": ["left_ctrl", "left_alt", "delete"]}}),
        ]
    )
    action._action_queue.join()
    print(json.dumps(keyboard.calls))
finally:
    action.close()
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=True,
        )
        calls = json.loads(result.stdout.strip())
        self.assertTrue(any(call[0] == "press" for call in calls))
        self.assertTrue(any(call[0] == "release" for call in calls))

    def test_rule_macro_trigger_executes_once(self):
        compiler = RuleCompiler({"click_pending_frames": 1, "ending_frames": 1}, 1920, 1080)
        action_calls = []

        class _ActionStub:
            def execute_macro_steps(self, steps):
                action_calls.append([step.step_type for step in steps])

            def set_pending_latency_origin_ts_ns(self, _ts):
                pass

        record = MacroRecord.build_new(
            name="Rule Macro",
            mode="mouse",
            trigger_kind=RULE_OVERRIDE_KIND,
            point_trigger=None,
            rule_trigger=MacroRuleTrigger(
                hand="either",
                rule_override=GestureRuleOverride(
                    conditions=[{"op": "hand_count_eq", "value": 1}],
                    pending_frames=1,
                    ending_frames=1,
                ),
            ),
            action_steps=[MacroActionStep.from_dict({"type": "left_click", "params": {}})],
        )
        recognizer = compiler.compile_ui_macro(_ActionStub(), record)
        hands = _hands_for_rule_trigger()

        self.assertFalse(recognizer.update(hands))
        self.assertTrue(recognizer.update(hands))
        self.assertFalse(recognizer.update(hands))
        self.assertEqual(action_calls, [["left_click"]])
        self.assertFalse(recognizer.consumes_events)

    def test_point_macro_trigger_executes_once(self):
        template = build_pose_template(
            "Point Macro Trigger",
            finger_curls={"index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
            thumb_curl=0.0,
        )
        compiler = RuleCompiler({"click_pending_frames": 1, "ending_frames": 1}, 1920, 1080)
        action_calls = []

        class _ActionStub:
            def execute_macro_steps(self, steps):
                action_calls.append([step.step_type for step in steps])

            def set_pending_latency_origin_ts_ns(self, _ts):
                pass

        record = MacroRecord.build_new(
            name="Point Macro",
            mode="mouse",
            trigger_kind=POINT_OVERRIDE_KIND,
            point_trigger=MacroPointTrigger(
                hand="right",
                pose_template=template,
                editor_pose_template=None,
                matcher_config=PoseMatcherConfig(),
            ),
            rule_trigger=None,
            action_steps=[MacroActionStep.from_dict({"type": "right_click", "params": {}})],
        )
        recognizer = compiler.compile_ui_macro(_ActionStub(), record)
        hands = _hands_for_point_trigger(template)

        self.assertFalse(recognizer.update(hands))
        self.assertTrue(recognizer.update(hands))
        self.assertFalse(recognizer.update(hands))
        self.assertEqual(action_calls, [["right_click"]])
        self.assertFalse(recognizer.consumes_events)

    def test_legacy_macro_chain_does_not_consume_events_while_progressing(self):
        class _StepRecognizer:
            def __init__(self):
                self.is_active = False

            def detect_gesture(self, _hands):
                return False, None

            def update(self, _hands):
                self.is_active = True
                return False

            def reset(self):
                self.is_active = False

        chain = MacroChainRecognizer(
            action=object(),
            priority=12,
            steps=[
                {"gesture_id": "step_one", "recognizer": _StepRecognizer(), "max_delay_ms": 1000},
                {"gesture_id": "step_two", "recognizer": _StepRecognizer(), "max_delay_ms": 1000},
            ],
            macro_action={"type": "scroll", "params": {"delta_x": 0, "delta_y": 1}},
            config={"debug_mode": False},
            screen_width=1920,
            screen_height=1080,
        )

        self.assertFalse(chain.consumes_events)

    def test_strategizer_loads_ui_macros_in_selected_mode_and_keeps_legacy_rules(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _ConfigStub(Path(tmp_dir) / "gesture_config.json")
            macro_store = MacroStore.from_config(config)
            macro_store.upsert(
                MacroRecord.build_new(
                    name="Keyboard Macro",
                    mode="keyboard",
                    trigger_kind=RULE_OVERRIDE_KIND,
                    point_trigger=None,
                    rule_trigger=MacroRuleTrigger(
                        hand="either",
                        rule_override=GestureRuleOverride(
                            conditions=[{"op": "hand_count_eq", "value": 1}],
                            pending_frames=1,
                            ending_frames=1,
                        ),
                    ),
                    action_steps=[MacroActionStep.from_dict({"type": "tap_key", "params": {"key": "a"}})],
                )
            )

            legacy_rules_path = Path(tmp_dir) / "legacy_rules.json"
            legacy_rules_path.write_text(
                """
                {
                  "version": 1,
                  "global": {"default_pending_frames": 1, "default_ending_frames": 1},
                  "custom_gestures": [
                    {
                      "id": "legacy_open",
                      "name": "Legacy Open",
                      "enabled": true,
                      "mode": "mouse",
                      "type": "pose",
                      "priority": 8,
                      "hand": "right",
                      "conditions": [{"op": "hand_count_eq", "value": 1}],
                      "action": {"type": "left_click", "params": {"at": "index.tip", "space": "camera"}}
                    }
                  ],
                  "custom_macros": []
                }
                """,
                encoding="utf-8",
            )

            class _ActionStub:
                def __init__(self):
                    self.executed_macros = []

                def left_click(self, *_args):
                    pass

                def right_click(self, *_args):
                    pass

                def move_cursor(self, *_args):
                    pass

                def scroll(self, *_args, **_kwargs):
                    pass

                def execute_macro_steps(self, steps):
                    self.executed_macros.append([step.step_type for step in steps])

                def set_pending_latency_origin_ts_ns(self, _ts):
                    pass

                def release_all_keys(self):
                    pass

            strategizer = Strategizer(_ActionStub(), config, 1920, 1080)
            strategizer.load_custom_rules(str(legacy_rules_path))
            self.assertTrue(any(getattr(recognizer, "name", "") == "Keyboard Macro" for recognizer in strategizer.keyboard_mode_gestures))
            self.assertGreaterEqual(len(strategizer._custom_gesture_instances), 2)

    def test_strategizer_does_not_auto_load_repo_root_legacy_rules(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _ConfigStub(Path(tmp_dir) / "gesture_config.json")

            class _ActionStub:
                def left_click(self, *_args):
                    pass

                def right_click(self, *_args):
                    pass

                def move_cursor(self, *_args):
                    pass

                def scroll(self, *_args, **_kwargs):
                    pass

                def execute_macro_steps(self, _steps):
                    pass

                def set_pending_latency_origin_ts_ns(self, _ts):
                    pass

                def release_all_keys(self):
                    pass

            strategizer = Strategizer(_ActionStub(), config, 1920, 1080)
            self.assertEqual(strategizer._custom_gesture_instances, [])


if __name__ == "__main__":
    unittest.main()
