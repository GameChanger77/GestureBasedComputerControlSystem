import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

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
from frontend.widgets.editors.macro_editor_dialog import MacroEditorDialog


class MacroEditorDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_new_editor_defaults_to_rule_pose_mouse_mode_with_no_shortcut(self):
        dialog = MacroEditorDialog(
            config_source={"click_pending_frames": 3, "ending_frames": 2},
            target_os="Windows",
        )
        self.assertEqual(dialog.trigger_editor.selected_kind(), RULE_OVERRIDE_KIND)
        self.assertEqual(dialog.trigger_editor.rule_editor.selected_trigger_type(), RULE_TRIGGER_TYPE_POSE)
        self.assertEqual(dialog.mode_combo.currentData(), "mouse")
        self.assertEqual(dialog.shortcut_editor.build_shortcut_keys(), [])
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
            shortcut_keys=["left_ctrl", "v"],
            target_os="Windows",
        )
        dialog = MacroEditorDialog(
            config_source={"click_pending_frames": 3, "ending_frames": 2},
            existing_record=record,
            target_os="Windows",
        )
        self.assertEqual(dialog.trigger_editor.selected_kind(), POINT_OVERRIDE_KIND)
        self.assertEqual(dialog.trigger_editor.hand_combo.currentData(), "left")
        self.assertEqual(dialog.shortcut_editor.build_shortcut_keys(), ["left_ctrl", "v"])
        dialog.close()

    def test_existing_swipe_trigger_reopens_swipe_editor(self):
        record = MacroRecord.build_new(
            name="Swipe Macro",
            mode="hotkey",
            trigger_kind=RULE_OVERRIDE_KIND,
            point_trigger=None,
            rule_trigger=MacroRuleTrigger(
                hand="either",
                trigger_type=RULE_TRIGGER_TYPE_SWIPE,
                rule_override=None,
                start_rule_override=GestureRuleOverride(
                    conditions=[{"op": "hand_fully_open"}],
                    pending_frames=1,
                    ending_frames=1,
                ),
                swipe_config=MacroSwipeConfig.from_dict(
                    {
                        "tracked_point": "index.tip",
                        "direction": "right",
                        "min_displacement": 0.18,
                        "min_speed": 0.70,
                        "min_smoothness": 0.75,
                        "start_confirm_frames": 2,
                        "timeout_frames": 16,
                    }
                ),
            ),
            shortcut_keys=["cmd", "shift", "4"],
            target_os="Darwin",
        )
        dialog = MacroEditorDialog(
            config_source={"click_pending_frames": 3, "ending_frames": 2},
            existing_record=record,
            target_os="Darwin",
        )
        self.assertEqual(dialog.trigger_editor.selected_kind(), RULE_OVERRIDE_KIND)
        self.assertEqual(dialog.trigger_editor.rule_editor.selected_trigger_type(), RULE_TRIGGER_TYPE_SWIPE)
        self.assertEqual(dialog.shortcut_editor.build_shortcut_keys(), ["left_cmd", "left_shift", "4"])
        dialog.close()

    def test_save_disabled_until_name_trigger_and_shortcut_are_valid(self):
        dialog = MacroEditorDialog(
            config_source={"click_pending_frames": 3, "ending_frames": 2},
            target_os="Windows",
        )
        self.assertFalse(dialog.save_button.isEnabled())
        dialog.name_edit.setText("New Macro")
        dialog.shortcut_editor._shortcut_keys = ["left_ctrl", "c"]
        dialog.shortcut_editor._refresh()
        dialog.trigger_editor.rule_editor.pose_editor._add_condition_editor({"op": "hand_fully_open"})
        dialog._refresh_can_save()
        self.assertTrue(dialog.save_button.isEnabled())
        dialog.close()

    def test_save_preserves_shortcut_keys(self):
        record = MacroRecord.build_new(
            name="Rule Macro",
            mode="keyboard",
            trigger_kind=RULE_OVERRIDE_KIND,
            point_trigger=None,
            rule_trigger=MacroRuleTrigger(
                hand="right",
                trigger_type=RULE_TRIGGER_TYPE_POSE,
                rule_override=GestureRuleOverride(
                    conditions=[{"op": "hand_fully_open"}],
                    pending_frames=1,
                    ending_frames=1,
                ),
                start_rule_override=None,
                swipe_config=None,
            ),
            shortcut_keys=["left_ctrl", "left_shift", "s"],
            target_os="Windows",
        )
        dialog = MacroEditorDialog(
            config_source={"click_pending_frames": 3, "ending_frames": 2},
            existing_record=record,
            target_os="Windows",
        )
        dialog._on_save_clicked()
        self.assertEqual(dialog.result_record.shortcut_keys, ["left_ctrl", "left_shift", "s"])
        self.assertEqual(dialog.result_record.rule_trigger.trigger_type, RULE_TRIGGER_TYPE_POSE)
        dialog.close()

    def test_dialog_uses_standard_window_controls_and_bounded_geometry(self):
        dialog = MacroEditorDialog(
            config_source={"click_pending_frames": 3, "ending_frames": 2},
            target_os="Linux",
        )
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

    def test_shortcut_key_combo_ignores_wheel_scrolling_but_keeps_editing(self):
        dialog = MacroEditorDialog(
            config_source={"click_pending_frames": 3, "ending_frames": 2},
            target_os="Windows",
        )

        class _WheelStub:
            def __init__(self):
                self.ignored = False

            def ignore(self):
                self.ignored = True

            def type(self):
                return QEvent.Type.Wheel

        wheel_event = _WheelStub()
        dialog.shortcut_editor.key_combo.wheelEvent(wheel_event)
        self.assertTrue(wheel_event.ignored)

        popup_wheel_event = _WheelStub()
        blocked = dialog.shortcut_editor.key_combo.eventFilter(
            dialog.shortcut_editor.key_combo.view(),
            popup_wheel_event,
        )
        self.assertTrue(blocked)
        self.assertTrue(popup_wheel_event.ignored)
        self.assertTrue(dialog.shortcut_editor.key_combo.isEditable())
        dialog.close()

    def test_macro_pose_condition_options_exclude_hand_exists_and_hand_count(self):
        dialog = MacroEditorDialog(
            config_source={"click_pending_frames": 3, "ending_frames": 2},
            target_os="Windows",
        )
        dialog.trigger_editor.rule_editor.pose_editor._add_condition_editor({"op": "hand_fully_open"})
        op_combo = dialog.trigger_editor.rule_editor.pose_editor._condition_editors[0].op_combo
        options = [op_combo.itemData(index) for index in range(op_combo.count())]
        self.assertNotIn("hand_exists", options)
        self.assertNotIn("hand_count_eq", options)
        self.assertIn("hand_fully_open", options)
        dialog.close()

    def test_macro_swipe_condition_options_exclude_hand_exists_and_hand_count(self):
        dialog = MacroEditorDialog(
            config_source={"click_pending_frames": 3, "ending_frames": 2},
            target_os="Windows",
        )
        dialog.trigger_editor.rule_editor._set_selected_trigger_type(RULE_TRIGGER_TYPE_SWIPE)
        dialog.trigger_editor.rule_editor.swipe_editor._add_condition_editor({"op": "hand_fully_open"})
        op_combo = dialog.trigger_editor.rule_editor.swipe_editor._condition_editors[0].op_combo
        options = [op_combo.itemData(index) for index in range(op_combo.count())]
        self.assertNotIn("hand_exists", options)
        self.assertNotIn("hand_count_eq", options)
        self.assertIn("hand_fully_open", options)
        dialog.close()


if __name__ == "__main__":
    unittest.main()
