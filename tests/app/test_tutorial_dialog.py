import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt

from frontend.widgets.tutorial.tutorial_dialog import TutorialDialog


class _FakeTracker:
    def __init__(self, running=True):
        self._running = running

    def isRunning(self):
        return self._running


class _FakeMainWindow:
    def __init__(self):
        self.hand_tracker = _FakeTracker(True)
        self.ensure_tracking_calls = 0

    def ensure_tracking_running(self):
        self.ensure_tracking_calls += 1
        return True


class _FakeStrategizer:
    def __init__(self):
        self.mode_name = "MOUSE"
        self.overlay_data = None

    def get_mode_name(self):
        return self.mode_name

    def get_keyboard_overlay_data(self):
        return self.overlay_data


class _FakeAction:
    def __init__(self):
        self.screen_origin_x = 0
        self.screen_origin_y = 0
        self.scope_calls = []
        self._events = []
        self._sequence = 0

    def set_tutorial_scope(self, *, bounds=None, capture_text=False):
        self.scope_calls.append(("set", bounds, capture_text))

    def clear_tutorial_scope(self):
        self.scope_calls.append(("clear", None, False))

    def get_action_events(self, *, after_sequence=0):
        return [event for event in self._events if event["sequence"] > after_sequence]

    def push_event(self, event_type, **payload):
        self._sequence += 1
        event = {"sequence": self._sequence, "type": event_type}
        event.update(payload)
        self._events.append(event)


class TutorialDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_starts_on_first_step_and_resets_on_reopen(self):
        parent = QWidget()
        fake_main_window = _FakeMainWindow()
        fake_action = _FakeAction()
        fake_strategizer = _FakeStrategizer()

        first = TutorialDialog(
            parent,
            main_window=fake_main_window,
            action=fake_action,
            strategizer=fake_strategizer,
            ui_mode="dev",
        )
        self.assertEqual(first.title_label.text(), "Move the mouse")
        first._controller.mark_current_complete()
        first._go_next()
        self.assertEqual(first.title_label.text(), "Perform a left click")
        first.close()

        second = TutorialDialog(
            parent,
            main_window=fake_main_window,
            action=fake_action,
            strategizer=fake_strategizer,
            ui_mode="dev",
        )
        self.assertEqual(second.title_label.text(), "Move the mouse")
        self.assertFalse(second.continue_button.isEnabled())
        self.assertEqual(second.continue_button.cursor().shape(), Qt.ForbiddenCursor)
        self.assertFalse(hasattr(second, "mode_badge"))
        second.close()

    def test_dev_mode_prod_only_steps_are_informational(self):
        dialog = TutorialDialog(
            QWidget(),
            main_window=_FakeMainWindow(),
            action=_FakeAction(),
            strategizer=_FakeStrategizer(),
            ui_mode="dev",
        )

        for _ in range(5):
            dialog._controller.mark_current_complete()
            dialog._go_next()

        self.assertEqual(dialog.title_label.text(), "Drag the keyboard")
        self.assertTrue(dialog.continue_button.isEnabled())
        dialog.close()

    def test_typing_step_consumes_tutorial_text_events(self):
        fake_action = _FakeAction()
        dialog = TutorialDialog(
            QWidget(),
            main_window=_FakeMainWindow(),
            action=fake_action,
            strategizer=_FakeStrategizer(),
            ui_mode="prod",
        )

        for _ in range(8):
            dialog._controller.mark_current_complete()
            dialog._go_next()

        self.assertEqual(dialog.title_label.text(), "Type on the keyboard")
        fake_action.push_event("type_text", text="hel")
        fake_action.push_event("type_text", text="lo")
        dialog._poll_runtime_state()

        self.assertEqual(dialog._typing_input.text(), "hello")
        self.assertTrue(dialog.continue_button.isEnabled())
        self.assertEqual(dialog.continue_button.cursor().shape(), Qt.PointingHandCursor)
        dialog.close()

    def test_global_event_hits_widget_uses_qt_global_coordinates(self):
        dialog = TutorialDialog(
            QWidget(),
            main_window=_FakeMainWindow(),
            action=_FakeAction(),
            strategizer=_FakeStrategizer(),
            ui_mode="prod",
        )
        dialog.show()
        self._app.processEvents()

        target = dialog._target_frame
        target_global = target.mapToGlobal(target.rect().center())
        self.assertTrue(
            dialog._global_event_hits_widget(
                {"global_x": target_global.x(), "global_y": target_global.y()},
                target,
            )
        )
        self.assertFalse(
            dialog._global_event_hits_widget(
                {"global_x": target_global.x() + 500, "global_y": target_global.y() + 500},
                target,
            )
        )
        dialog.close()

    def test_continue_button_uses_lock_then_unlock_icon(self):
        dialog = TutorialDialog(
            QWidget(),
            main_window=_FakeMainWindow(),
            action=_FakeAction(),
            strategizer=_FakeStrategizer(),
            ui_mode="prod",
        )

        locked_icon = dialog.continue_button.icon().cacheKey()
        self.assertFalse(dialog.continue_button.isEnabled())

        dialog._controller.mark_current_complete()
        dialog._update_navigation()

        unlocked_icon = dialog.continue_button.icon().cacheKey()
        self.assertTrue(dialog.continue_button.isEnabled())
        self.assertNotEqual(locked_icon, unlocked_icon)
        dialog.close()

    def test_step_completion_starts_countdown_and_confetti(self):
        dialog = TutorialDialog(
            QWidget(),
            main_window=_FakeMainWindow(),
            action=_FakeAction(),
            strategizer=_FakeStrategizer(),
            ui_mode="prod",
        )

        dialog._mark_current_complete("Done")

        self.assertTrue(dialog._completion_countdown_active)
        self.assertTrue(dialog.confetti_overlay.is_active)
        self.assertTrue(dialog.continue_button.isEnabled())
        self.assertIn("(3)", dialog.continue_button.text())
        dialog.close()

    def test_auto_advance_moves_to_next_step(self):
        dialog = TutorialDialog(
            QWidget(),
            main_window=_FakeMainWindow(),
            action=_FakeAction(),
            strategizer=_FakeStrategizer(),
            ui_mode="prod",
        )

        dialog._mark_current_complete("Done")
        dialog._completion_deadline = time.monotonic() - 0.1
        dialog._on_auto_advance_tick()

        self.assertEqual(dialog.title_label.text(), "Perform a left click")
        self.assertFalse(dialog._completion_countdown_active)
        self.assertEqual(dialog.continue_button.text(), "Continue")
        dialog.close()

    def test_back_cancels_active_countdown(self):
        dialog = TutorialDialog(
            QWidget(),
            main_window=_FakeMainWindow(),
            action=_FakeAction(),
            strategizer=_FakeStrategizer(),
            ui_mode="prod",
        )
        dialog._controller.mark_current_complete()
        dialog._go_next()
        self.assertEqual(dialog.title_label.text(), "Perform a left click")

        dialog._mark_current_complete("Done")
        self.assertTrue(dialog._completion_countdown_active)

        dialog._go_back()

        self.assertEqual(dialog.title_label.text(), "Move the mouse")
        self.assertFalse(dialog._completion_countdown_active)
        self.assertEqual(dialog.continue_button.text(), "Continue")
        dialog.close()

    def test_final_step_auto_finishes_after_countdown(self):
        dialog = TutorialDialog(
            QWidget(),
            main_window=_FakeMainWindow(),
            action=_FakeAction(),
            strategizer=_FakeStrategizer(),
            ui_mode="prod",
        )

        for _ in range(dialog._controller.total_steps - 1):
            dialog._controller.mark_current_complete()
            dialog._go_next()

        self.assertEqual(dialog.title_label.text(), "Switch back to mouse mode")
        dialog._mark_current_complete("Done")
        self.assertIn("Finish (3)", dialog.continue_button.text())

        dialog._completion_deadline = time.monotonic() - 0.1
        dialog._on_auto_advance_tick()

        self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)

    def test_manual_continue_stops_countdown(self):
        dialog = TutorialDialog(
            QWidget(),
            main_window=_FakeMainWindow(),
            action=_FakeAction(),
            strategizer=_FakeStrategizer(),
            ui_mode="prod",
        )

        dialog._mark_current_complete("Done")
        dialog._go_next()

        self.assertEqual(dialog.title_label.text(), "Perform a left click")
        self.assertFalse(dialog._completion_countdown_active)
        dialog.close()

    def test_drag_keyboard_step_latches_origin_from_first_live_rect(self):
        strategizer = _FakeStrategizer()
        dialog = TutorialDialog(
            QWidget(),
            main_window=_FakeMainWindow(),
            action=_FakeAction(),
            strategizer=strategizer,
            ui_mode="prod",
        )

        for _ in range(5):
            dialog._controller.mark_current_complete()
            dialog._go_next()

        self.assertEqual(dialog.title_label.text(), "Drag the keyboard")
        dialog._drag_rect_origin = None

        strategizer.overlay_data = {
            "prod_window_locked": True,
            "prod_window_rect_px": {"x": 100, "y": 200, "w": 900, "h": 300},
        }
        dialog._process_runtime_completion()
        self.assertEqual(dialog._drag_rect_origin, (100, 200, 900, 300))
        self.assertFalse(dialog.continue_button.isEnabled())

        strategizer.overlay_data = {
            "prod_window_locked": False,
            "prod_window_rect_px": {"x": 160, "y": 220, "w": 900, "h": 300},
        }
        dialog._process_runtime_completion()

        self.assertTrue(dialog.continue_button.isEnabled())
        self.assertTrue(dialog._completion_countdown_active)
        dialog.close()


if __name__ == "__main__":
    unittest.main()
