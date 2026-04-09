import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.Strategizer import Strategizer
from backend.custom_rules.RuleLoader import RuleLoader
from backend.gesture_remap.rule_overrides import GestureRuleOverride, RULE_OVERRIDE_KIND
from backend.macros.macro_models import (
    MacroRecord,
    MacroRuleTrigger,
    RULE_TRIGGER_TYPE_POSE,
)
from backend.macros.macro_store import MacroStore


class _ActionStub:
    detected_os = "Windows"

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

    def tap_hotkey(self, *_args, **_kwargs):
        return True

    def set_pending_latency_origin_ts_ns(self, _ts):
        pass

    def release_all_keys(self):
        pass


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
        self.config_path = Path(config_path)
        self.config = self


def _write_legacy_rules(path: Path, *, include_custom_macros=False, macro_action_type=False):
    payload = {
        "version": 1,
        "global": {"default_pending_frames": 1, "default_ending_frames": 1},
        "custom_gestures": [
            {
                "id": "legacy_open_palm",
                "name": "Legacy Open Palm",
                "enabled": True,
                "mode": "mouse",
                "type": "pose",
                "priority": 8,
                "hand": "right",
                "conditions": [
                    {
                        "op": "only_fingers_extended",
                        "fingers": ["index", "middle", "ring", "pinky"],
                        "threshold_deg": 155,
                    }
                ],
                "confirm": {"pending_frames": 1, "ending_frames": 1},
                "action": (
                    {"type": "macro", "params": {"keys": ["left_ctrl", "c"]}}
                    if macro_action_type
                    else {"type": "mouse_move", "params": {"at": "index.tip", "space": "camera"}}
                ),
            }
        ],
    }
    if include_custom_macros:
        payload["custom_macros"] = []
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_ui_macro(config):
    macro_store = MacroStore.from_config(config, target_os="Windows")
    macro_store.upsert(
        MacroRecord.build_new(
            name="UI Macro",
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
        )
    )


class LegacyCustomRulesLoadingTests(unittest.TestCase):
    def test_startup_does_not_load_legacy_rules_without_flag(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "gesture_config.json"
            config = _ConfigStub(config_path)
            _write_legacy_rules(config_path.with_name("gesture_custom_rules.json"))
            _write_ui_macro(config)

            strategizer = Strategizer(
                _ActionStub(),
                config,
                1920,
                1080,
                load_legacy_custom_rules=False,
            )

            mouse_names = [getattr(gesture, "debug_name", gesture.__class__.__name__) for gesture in strategizer.mouse_mode_gestures]
            self.assertNotIn("Legacy Open Palm", mouse_names)
            self.assertEqual(len(strategizer._custom_gesture_instances), 1)

    def test_startup_loads_legacy_rules_with_flag(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "gesture_config.json"
            config = _ConfigStub(config_path)
            _write_legacy_rules(config_path.with_name("gesture_custom_rules.json"))
            _write_ui_macro(config)

            strategizer = Strategizer(
                _ActionStub(),
                config,
                1920,
                1080,
                load_legacy_custom_rules=True,
            )

            mouse_class_names = [gesture.__class__.__name__ for gesture in strategizer.mouse_mode_gestures]
            mouse_macro_names = [getattr(gesture, "name", "") for gesture in strategizer.mouse_mode_gestures]
            self.assertIn("RuleSnapshotGesture", mouse_class_names)
            self.assertIn("UI Macro", mouse_macro_names)
            self.assertEqual(len(strategizer.mouse_mode_gestures), 6)
            self.assertEqual(len(strategizer._custom_gesture_instances), 2)

    def test_loader_rejects_legacy_custom_macros_field(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            rules_path = Path(tmp_dir) / "gesture_custom_rules.json"
            _write_legacy_rules(rules_path, include_custom_macros=True)

            with self.assertRaisesRegex(ValueError, "custom_macros"):
                RuleLoader(str(rules_path)).load()

    def test_loader_rejects_legacy_macro_action_type(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            rules_path = Path(tmp_dir) / "gesture_custom_rules.json"
            _write_legacy_rules(rules_path, macro_action_type=True)

            with self.assertRaisesRegex(ValueError, "action.type='macro'"):
                RuleLoader(str(rules_path)).load()


class MainLegacyFlagWiringTests(unittest.TestCase):
    def test_parse_args_exposes_legacy_flag(self):
        from main import parse_args

        args = parse_args(["main.py", "--dev", "--load-legacy-custom-rules"])
        self.assertTrue(args.dev)
        self.assertTrue(args.load_legacy_custom_rules)

    def test_component_factory_passes_legacy_flag_to_strategizer(self):
        from main import create_backend_components

        with patch("backend.Action.Action") as action_cls, patch("backend.HandTracker.HandTracker") as tracker_cls, patch(
            "backend.Strategizer.Strategizer"
        ) as strategizer_cls:
            action_cls.return_value = object()
            tracker_cls.return_value = object()
            create_backend_components(
                screen_width=1920,
                screen_height=1080,
                config_path="gesture_config.json",
                ui_mode="dev",
                load_legacy_custom_rules=True,
            )

        self.assertTrue(strategizer_cls.called)
        self.assertTrue(strategizer_cls.call_args.kwargs["load_legacy_custom_rules"])


if __name__ == "__main__":
    unittest.main()
