import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from backend.gesture_remap.pose_templates import PoseMatcherConfig, build_pose_template
from backend.gesture_remap.rule_overrides import GestureRuleOverride, POINT_OVERRIDE_KIND, RULE_OVERRIDE_KIND
from backend.macros.macro_models import MacroActionStep, MacroPointTrigger, MacroRecord, MacroRuleTrigger
from frontend.widgets.editors.macro_editor_dialog import MacroEditorDialog


class MacroEditorDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_new_editor_defaults_to_rule_based_mouse_mode_with_no_steps(self):
        dialog = MacroEditorDialog(config_source={"click_pending_frames": 3, "ending_frames": 2})
        self.assertEqual(dialog.trigger_editor.selected_kind(), RULE_OVERRIDE_KIND)
        self.assertEqual(dialog.mode_combo.currentData(), "mouse")
        self.assertEqual(len(dialog._step_editors), 0)
        dialog.close()

    def test_existing_point_trigger_reopens_point_editor(self):
        template = build_pose_template(
            "Saved Trigger",
            finger_curls={"index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
            thumb_curl=0.0,
        )
        record = MacroRecord.build_new(
            name="Point Macro",
            mode="mouse",
            trigger_kind=POINT_OVERRIDE_KIND,
            point_trigger=MacroPointTrigger(
                hand="left",
                pose_template=template,
                editor_pose_template=None,
                matcher_config=PoseMatcherConfig(),
            ),
            rule_trigger=None,
            action_steps=[MacroActionStep.from_dict({"type": "left_click", "params": {}})],
        )
        dialog = MacroEditorDialog(config_source={"click_pending_frames": 3, "ending_frames": 2}, existing_record=record)
        self.assertEqual(dialog.trigger_editor.selected_kind(), POINT_OVERRIDE_KIND)
        self.assertEqual(dialog.trigger_editor.hand_combo.currentData(), "left")
        dialog.close()

    def test_save_preserves_action_order(self):
        record = MacroRecord.build_new(
            name="Rule Macro",
            mode="keyboard",
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
            action_steps=[
                MacroActionStep.from_dict({"type": "key_down", "params": {"key": "left_ctrl"}}),
                MacroActionStep.from_dict({"type": "tap_key", "params": {"key": "a"}}),
                MacroActionStep.from_dict({"type": "key_up", "params": {"key": "left_ctrl"}}),
            ],
        )
        dialog = MacroEditorDialog(config_source={"click_pending_frames": 3, "ending_frames": 2}, existing_record=record)
        dialog._on_save_clicked()
        self.assertEqual(
            [step.step_type for step in dialog.result_record.action_steps],
            ["key_down", "tap_key", "key_up"],
        )
        dialog.close()

    def test_save_disabled_until_name_trigger_and_step_are_valid(self):
        dialog = MacroEditorDialog(config_source={"click_pending_frames": 3, "ending_frames": 2})
        self.assertFalse(dialog.save_button.isEnabled())
        dialog.name_edit.setText("New Macro")
        dialog._add_step_editor()
        dialog.trigger_editor.rule_editor._add_condition_editor({"op": "hand_count_eq", "value": 1})
        dialog._refresh_can_save()
        self.assertTrue(dialog.save_button.isEnabled())
        dialog.close()

    def test_dialog_uses_standard_window_controls_and_bounded_geometry(self):
        dialog = MacroEditorDialog(config_source={"click_pending_frames": 3, "ending_frames": 2})
        flags = dialog.windowFlags()
        self.assertTrue(bool(flags & Qt.Window))
        self.assertTrue(bool(flags & Qt.WindowMinimizeButtonHint))
        self.assertTrue(bool(flags & Qt.WindowMaximizeButtonHint))
        self.assertTrue(dialog.isSizeGripEnabled())

        screen_geometry = QGuiApplication.primaryScreen().availableGeometry()
        self.assertLess(dialog.width(), 1420)
        self.assertLessEqual(dialog.width(), screen_geometry.width())
        self.assertLessEqual(dialog.height(), screen_geometry.height())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
