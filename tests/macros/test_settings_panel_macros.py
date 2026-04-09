import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from backend.gesture_remap.pose_templates import PoseMatcherConfig, build_pose_template
from backend.gesture_remap.rule_overrides import GestureRuleOverride, POINT_OVERRIDE_KIND, RULE_OVERRIDE_KIND
from backend.macros.macro_models import (
    MacroPointTrigger,
    MacroRecord,
    MacroRuleTrigger,
    RULE_TRIGGER_TYPE_POSE,
)
from backend.macros.macro_store import MacroStore
from backend.platforms.KeyboardBackendFactory import normalize_os_name
from frontend.widgets.settings.settings_panel import SettingsPanel


class _ConfigStub:
    def __init__(self, config_path):
        self.config_path = Path(config_path)
        self.config = {
            "keyboard_layout": "qwerty",
            "keyboard_theme": "dark",
            "camera_index": 0,
            "camera_backend": 0,
            "camera_device_path": "",
            "camera_device_name": "",
            "finger_extension_angle": 155.0,
            "scroll_sensitivity": 100,
            "pinch_threshold": 0.30,
            "mouse_tracking_pending_frames": 1,
            "click_pending_frames": 3,
            "scroll_pending_frames": 2,
            "ending_frames": 2,
            "keyboard_mode_entry_pending_frames": 6,
            "keyboard_mode_exit_pending_frames": 5,
            "keyboard_mode_exit_max_openness": 0.16,
            "keyboard_mode_exit_max_extension_ratio": 0.90,
            "keyboard_mode_exit_max_avg_finger_angle": 145.0,
        }


class SettingsPanelMacrosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_macros_page_exists_in_dev_and_prod(self):
        for ui_mode in ("dev", "prod"):
            panel = SettingsPanel(ui_mode=ui_mode)
            page_names = [panel._submenu_list.item(i).text() for i in range(panel._submenu_list.count())]
            self.assertIn("Macros", page_names)

    def test_macro_page_reflects_trigger_kind_and_shortcut(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "gesture_config.json"
            store = MacroStore(config_path.with_name("gesture_macros.json"), target_os="Windows")
            store.upsert(
                MacroRecord.build_new(
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
            )
            store.upsert(
                MacroRecord.build_new(
                    name="Point Macro",
                    mode="keyboard",
                    trigger_kind=POINT_OVERRIDE_KIND,
                    point_trigger=MacroPointTrigger(
                        hand="left",
                        pose_template=build_pose_template(
                            "Point Macro Trigger",
                            finger_curls={"index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
                            thumb_curl=0.0,
                        ),
                        editor_pose_template=None,
                        matcher_config=PoseMatcherConfig(),
                    ),
                    rule_trigger=None,
                    shortcut_keys=["left_ctrl", "left_shift", "s"],
                    target_os="Windows",
                )
            )

            panel = SettingsPanel(ui_mode="prod")
            panel.load_from_config(_ConfigStub(config_path))

            self.assertEqual(panel._macro_settings_page.snapshot_for("Rule Macro")["trigger"], "Rule-Based")
            self.assertEqual(panel._macro_settings_page.snapshot_for("Point Macro")["trigger"], "3D Hand Model")
            self.assertTrue(panel._macro_settings_page.snapshot_for("Rule Macro")["shortcut"])

    def test_create_macro_launches_editor_with_validation_and_target_os(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "gesture_config.json"
            panel = SettingsPanel(ui_mode="dev")
            panel.load_from_config(_ConfigStub(config_path))
            captured = {}

            class _DialogStub:
                def __init__(self, config_source, existing_record=None, validate_point_trigger_callback=None, target_os=None, parent=None):
                    captured["config_source"] = config_source
                    captured["existing_record"] = existing_record
                    captured["validate_callback"] = validate_point_trigger_callback
                    captured["target_os"] = target_os
                    self.result_record = None

                def exec(self):
                    return QDialog.DialogCode.Rejected

            with patch("frontend.widgets.settings.macro_settings_page.MacroEditorDialog", _DialogStub):
                panel._macro_settings_page._on_create_clicked()

            self.assertIsInstance(captured["config_source"], dict)
            self.assertIsNone(captured["existing_record"])
            self.assertTrue(callable(captured["validate_callback"]))
            self.assertEqual(captured["target_os"], normalize_os_name())

    def test_macro_page_uses_card_empty_state_when_no_macros(self):
        panel = SettingsPanel(ui_mode="prod")
        snapshot = panel._macro_settings_page.snapshot_for("Missing")
        self.assertIsNone(snapshot)

    def test_toggle_macro_emits_settings_panel_signal(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "gesture_config.json"
            store = MacroStore(config_path.with_name("gesture_macros.json"), target_os="Windows")
            record = store.upsert(
                MacroRecord.build_new(
                    name="Toggle Macro",
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
                    shortcut_keys=["left_ctrl", "x"],
                    target_os="Windows",
                )
            )

            panel = SettingsPanel(ui_mode="prod")
            panel.load_from_config(_ConfigStub(config_path))
            signals = []
            panel.macro_settings_changed.connect(lambda: signals.append("changed"))

            panel._macro_settings_page._toggle_macro(record.id)

            self.assertEqual(signals, ["changed"])
            self.assertEqual(panel._macro_settings_page.snapshot_for("Toggle Macro")["state"], "Disabled")


if __name__ == "__main__":
    unittest.main()
