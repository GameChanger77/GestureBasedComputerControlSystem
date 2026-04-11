import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.HandsData import HandsData
from backend.Strategizer import ControlMode, Strategizer
from backend.custom_rules.RuleCompiler import RuleCompiler
from backend.gesture_remap.pose_templates import PoseMatcherConfig, build_pose_template
from backend.gesture_remap.rule_overrides import GestureRuleOverride, POINT_OVERRIDE_KIND, RULE_OVERRIDE_KIND
from backend.macros.macro_models import (
    MacroPointTrigger,
    MacroRecord,
    MacroRuleTrigger,
    MacroSwipeConfig,
    RULE_TRIGGER_TYPE_POSE,
    RULE_TRIGGER_TYPE_SWIPE,
)
from backend.macros.macro_store import MacroStore
from backend.platforms.KeyboardBackendFactory import normalize_os_name


class _ActionRecorder:
    detected_os = "Windows"

    def __init__(self):
        self.hotkeys = []

    def tap_hotkey(self, keys):
        self.hotkeys.append(list(keys))
        return True

    def left_click(self, *_args, **_kwargs):
        pass

    def right_click(self, *_args, **_kwargs):
        pass

    def move_cursor(self, *_args, **_kwargs):
        pass

    def scroll(self, *_args, **_kwargs):
        pass

    def set_pending_latency_origin_ts_ns(self, _ts):
        pass

    def release_all_keys(self):
        pass


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


class _LowPriorityGesture:
    def __init__(self):
        self.priority = 1
        self.debug_name = "Low Priority Gesture"
        self.suppresses_lower_priorities_while_active = False
        self.consumes_events = False
        self.update_calls = 0
        self._active = False
        self._debug_last_detected = False
        self._debug_last_action_executed = False
        self._debug_last_note = ""

    def update(self, _hands_data, frame_capture_ts_ns=None):
        self.update_calls += 1
        self._active = True
        self._debug_last_detected = True
        self._debug_last_action_executed = True
        return True

    def reset(self):
        self._active = False

    @property
    def is_active(self):
        return self._active

    @property
    def current_state(self):
        return "active" if self._active else "idle"


def _blank_hand(x_index_tip=None):
    hand = np.zeros((21, 3), dtype=np.float32)
    if x_index_tip is not None:
        hand[8] = np.array([x_index_tip, 0.0, 0.0], dtype=np.float32)
    return hand


def _no_hands():
    return HandsData({}, {})


def _hands_for_rule_trigger():
    hand = _blank_hand()
    return HandsData({"Right": hand.copy()}, {"Right": hand.copy()})


def _hands_for_point_trigger(template):
    return HandsData({"Right": template.as_array().copy()}, {})


def _hands_for_swipe_frame(x_index_tip):
    wrist_hand = _blank_hand()
    camera_hand = _blank_hand(x_index_tip=x_index_tip)
    return HandsData({"Right": wrist_hand}, {"Right": camera_hand})


class MacroRuntimeTests(unittest.TestCase):
    def test_rule_macro_trigger_fires_once_per_activation(self):
        compiler = RuleCompiler({"click_pending_frames": 1, "ending_frames": 1}, 1920, 1080)
        action = _ActionRecorder()
        recognizer = compiler.compile_ui_macro(
            action,
            MacroRecord.build_new(
                name="Rule Macro",
                mode="mouse",
                trigger_kind=RULE_OVERRIDE_KIND,
                point_trigger=None,
                rule_trigger=MacroRuleTrigger(
                    hand="either",
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
            ),
        )

        hands = _hands_for_rule_trigger()
        self.assertFalse(recognizer.update(hands))
        self.assertTrue(recognizer.update(hands))
        self.assertFalse(recognizer.update(hands))
        self.assertEqual(action.hotkeys, [["left_ctrl", "c"]])
        self.assertTrue(recognizer.suppresses_lower_priorities_while_active)

        self.assertFalse(recognizer.update(_no_hands()))
        self.assertFalse(recognizer.update(_no_hands()))
        self.assertFalse(recognizer.update(hands))
        self.assertTrue(recognizer.update(hands))
        self.assertEqual(action.hotkeys, [["left_ctrl", "c"], ["left_ctrl", "c"]])

    def test_point_macro_trigger_fires_once_per_activation(self):
        template = build_pose_template(
            "Point Macro Trigger",
            finger_curls={"index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
            thumb_curl=0.0,
        )
        compiler = RuleCompiler({"click_pending_frames": 1, "ending_frames": 1}, 1920, 1080)
        action = _ActionRecorder()
        recognizer = compiler.compile_ui_macro(
            action,
            MacroRecord.build_new(
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
                shortcut_keys=["left_ctrl", "left_shift", "s"],
                target_os="Windows",
            ),
        )

        hands = _hands_for_point_trigger(template)
        self.assertFalse(recognizer.update(hands))
        self.assertTrue(recognizer.update(hands))
        self.assertFalse(recognizer.update(hands))
        self.assertEqual(action.hotkeys, [["left_ctrl", "left_shift", "s"]])
        self.assertTrue(recognizer.suppresses_lower_priorities_while_active)

    def test_swipe_macro_trigger_fires_once_per_swipe_until_rearmed(self):
        compiler = RuleCompiler({"click_pending_frames": 1, "ending_frames": 1}, 1920, 1080)
        action = _ActionRecorder()
        recognizer = compiler.compile_ui_macro(
            action,
            MacroRecord.build_new(
                name="Swipe Macro",
                mode="hotkey",
                trigger_kind=RULE_OVERRIDE_KIND,
                point_trigger=None,
                rule_trigger=MacroRuleTrigger(
                    hand="right",
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
                            "direction": "right",
                            "min_displacement": 0.20,
                            "min_speed": 0.10,
                            "min_smoothness": 0.95,
                            "start_confirm_frames": 2,
                            "timeout_frames": 18,
                        }
                    ),
                ),
                shortcut_keys=["left_ctrl", "v"],
                target_os="Windows",
            ),
        )

        for x_value in (0.00, 0.03, 0.10, 0.18, 0.27, 0.36):
            recognizer.update(_hands_for_swipe_frame(x_value))
        self.assertEqual(action.hotkeys, [["left_ctrl", "v"]])

        for x_value in (0.45, 0.52, 0.60):
            recognizer.update(_hands_for_swipe_frame(x_value))
        self.assertEqual(action.hotkeys, [["left_ctrl", "v"]])

        recognizer.update(_no_hands())
        for x_value in (0.00, 0.03, 0.10, 0.18, 0.27, 0.36):
            recognizer.update(_hands_for_swipe_frame(x_value))
        self.assertEqual(action.hotkeys, [["left_ctrl", "v"], ["left_ctrl", "v"]])

    def test_strategizer_suppresses_lower_priority_gesture_while_macro_is_active(self):
        action = _ActionRecorder()
        config = _ConfigStub(Path(tempfile.gettempdir()) / "macro_runtime_config.json")
        strategizer = Strategizer(action, config, 1920, 1080)
        compiler = RuleCompiler(config, 1920, 1080)
        high_priority_macro = compiler.compile_ui_macro(
            action,
            MacroRecord.build_new(
                name="Blocking Macro",
                mode="mouse",
                trigger_kind=RULE_OVERRIDE_KIND,
                point_trigger=None,
                rule_trigger=MacroRuleTrigger(
                    hand="either",
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
            ),
        )
        low_priority_gesture = _LowPriorityGesture()

        strategizer.switch_mode_gestures = []
        strategizer.mouse_mode_gestures = [low_priority_gesture, high_priority_macro]
        strategizer._rebuild_sorted_gestures(ControlMode.MOUSE)

        hands = _hands_for_rule_trigger()
        strategizer.strategize(hands)
        strategizer.strategize(hands)
        strategizer.strategize(hands)

        self.assertEqual(action.hotkeys, [["left_ctrl", "c"]])
        self.assertEqual(low_priority_gesture.update_calls, 1)

    def test_strategizer_loads_ui_macros_in_selected_mode(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _ConfigStub(Path(tmp_dir) / "gesture_config.json")
            macro_store = MacroStore.from_config(config, target_os="Windows")
            macro_store.upsert(
                MacroRecord.build_new(
                    name="Keyboard Macro",
                    mode="keyboard",
                    trigger_kind=RULE_OVERRIDE_KIND,
                    point_trigger=None,
                    rule_trigger=MacroRuleTrigger(
                        hand="either",
                        trigger_type=RULE_TRIGGER_TYPE_POSE,
                        rule_override=GestureRuleOverride(
                            conditions=[{"op": "hand_count_eq", "value": 1}],
                            pending_frames=1,
                            ending_frames=1,
                        ),
                        start_rule_override=None,
                        swipe_config=None,
                    ),
                    shortcut_keys=["left_ctrl", "a"],
                    target_os="Windows",
                )
            )

            strategizer = Strategizer(_ActionRecorder(), config, 1920, 1080)
            mouse_names = [getattr(gesture, "name", "") for gesture in strategizer.mouse_mode_gestures]
            keyboard_names = [getattr(gesture, "name", "") for gesture in strategizer.keyboard_mode_gestures]

            self.assertNotIn("Keyboard Macro", mouse_names)
            self.assertIn("Keyboard Macro", keyboard_names)

    def test_action_tap_hotkey_uses_shortcut_normalization(self):
        script = """
import json
from backend.Action import Action
from backend.platforms.KeyboardBackendFactory import normalize_os_name

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
action = Action(mouse=mouse, keyboard_test=keyboard, osType=normalize_os_name())
try:
    action.tap_hotkey(["ctrl", "c"])
    action._action_queue.join()
    print(json.dumps(keyboard.calls))
finally:
    action.close()
"""
        result = json.loads(
            subprocess.run(
                [sys.executable, "-c", script],
                cwd=Path(__file__).resolve().parents[2],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
        self.assertTrue(any(call[0] == "press" for call in result))
        self.assertTrue(any(call[0] == "release" for call in result))


if __name__ == "__main__":
    unittest.main()
