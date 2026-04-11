import os
import unittest
import numpy as np

from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from backend.HandsData import HandsData
from frontend.main_window import MainWindow


class _TestableMainWindow(MainWindow):
    def __init__(self, *args, **kwargs):
        self._test_sender = None
        super().__init__(*args, **kwargs)

    def sender(self):
        return self._test_sender


class _FakeTracker:
    def isRunning(self):
        return False


class _FakeStartTracker(_FakeTracker):
    def __init__(self, start_result=True):
        self.start_result = bool(start_result)
        self.start_calls = []

    def start_tracking(self, **kwargs):
        self.start_calls.append(dict(kwargs))
        return self.start_result


class _FakeProductionKeyboardWindow:
    def __init__(self):
        self.overlay_calls = []
        self.closed = False

    def set_overlay_data(self, overlay_data):
        self.overlay_calls.append(overlay_data)

    def close(self):
        self.closed = True


class _FakeShortcutFeedbackOverlay:
    def __init__(self):
        self.show_calls = []
        self.hide_calls = 0
        self.closed = False

    def show_shortcut(self, text, global_x, global_y):
        self.show_calls.append((text, global_x, global_y))

    def hide_feedback(self):
        self.hide_calls += 1

    def close(self):
        self.closed = True


class MainWindowTrackerStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_stale_tracking_stopped_signal_is_ignored(self):
        window = _TestableMainWindow(ui_mode="prod")
        current_tracker = _FakeTracker()
        stale_tracker = _FakeTracker()
        window.hand_tracker = current_tracker
        window._set_start_button_running(True)
        window._set_status_text("Status: Running")
        window._test_sender = stale_tracker

        window.on_tracking_stopped()

        self.assertEqual(window.start_button.text(), "Stop Tracking")
        self.assertEqual(window.status_label.text(), "Status: Running")
        window.close()

    def test_current_tracking_started_signal_sets_running_state(self):
        window = _TestableMainWindow(ui_mode="prod")
        current_tracker = _FakeTracker()
        window.hand_tracker = current_tracker
        window._set_start_button_running(False)
        window._test_sender = current_tracker

        window.on_tracking_started()

        self.assertEqual(window.start_button.text(), "Stop Tracking")
        self.assertEqual(window.status_label.text(), "Status: Running")
        window.close()

    def test_dev_landmarks_update_populates_gesture_debug_widget(self):
        window = _TestableMainWindow(ui_mode="dev")
        hands = HandsData({"Right": np.zeros((21, 3), dtype=np.float32)}, {"Right": np.zeros((21, 3), dtype=np.float32)})
        snapshot = {
            "mode": "MOUSE",
            "hands": [
                {
                    "side": "Left",
                    "present": False,
                    "extended_fingers": [],
                    "curled_fingers": ["Thumb", "Index", "Middle", "Ring", "Pinky"],
                    "detected_pinches": [],
                },
                {
                    "side": "Right",
                    "present": True,
                    "extended_fingers": ["Index"],
                    "curled_fingers": ["Thumb", "Middle", "Ring", "Pinky"],
                    "detected_pinches": ["Thumb + Middle"],
                },
            ],
            "mode_switch_candidates": [],
            "mode_candidates": [
                {
                    "name": "Mouse Move",
                    "priority": 1,
                    "state": "active",
                    "detected": True,
                    "active": True,
                    "executed": True,
                    "suppressed": False,
                    "note": "",
                }
            ],
            "winning_action": {"name": "Mouse Move", "priority": 1, "note": ""},
        }

        window.on_landmarks_detected(
            {
                "smoothed_hands_data": hands,
                "gesture_debug": snapshot,
                "metrics": {},
            },
            None,
        )

        self.assertIn("Mouse Move", window.gesture_debug_widget._action_value.text())
        self.assertIn("Cursor:", window.gesture_debug_widget._action_value.text())
        self.assertIn("Thumb + Middle", window.gesture_debug_widget._hand_pinch_labels["Right"].text())
        window.close()

    def test_prod_landmarks_update_refreshes_mode_badge_and_hands_off_overlay(self):
        window = _TestableMainWindow(ui_mode="prod")
        fake_window = _FakeProductionKeyboardWindow()
        overlay = {
            "enabled": True,
            "surface": "prod",
            "prod_window_rect_px": {"x": 100, "y": 200, "w": 900, "h": 300},
        }
        window.production_keyboard_window = fake_window
        window.strategizer = SimpleNamespace(
            get_mode_name=lambda: "KEYBOARD",
            get_keyboard_overlay_data=lambda: overlay,
        )

        window.on_landmarks_detected({"metrics": {}}, None)

        self.assertEqual(window.mode_label.text(), "Mode: KEYBOARD")
        self.assertEqual(window.mode_label.property("badgeTone"), "warning")
        self.assertEqual(fake_window.overlay_calls, [overlay])
        window.close()

    def test_shortcut_feedback_overlay_shows_for_new_hotkey_event(self):
        window = _TestableMainWindow(ui_mode="prod")
        fake_overlay = _FakeShortcutFeedbackOverlay()
        window.shortcut_feedback_overlay = fake_overlay
        window.action = SimpleNamespace(
            get_action_events=lambda after_sequence=0: (
                []
                if after_sequence >= 5
                else [
                    {
                        "sequence": 5,
                        "type": "tap_hotkey",
                        "shortcut_label": "Ctrl + Shift + S",
                        "global_x": 640,
                        "global_y": 360,
                    }
                ]
            )
        )

        window._refresh_shortcut_feedback_overlay()
        window._refresh_shortcut_feedback_overlay()

        self.assertEqual(fake_overlay.show_calls, [("Ctrl + Shift + S", 640, 360)])
        window.close()

    def test_shortcut_feedback_overlay_shows_for_mode_change_event(self):
        window = _TestableMainWindow(ui_mode="prod")
        fake_overlay = _FakeShortcutFeedbackOverlay()
        window.shortcut_feedback_overlay = fake_overlay
        window.action = SimpleNamespace(
            get_action_events=lambda after_sequence=0: (
                []
                if after_sequence >= 9
                else [
                    {
                        "sequence": 9,
                        "type": "overlay_feedback",
                        "label": "Hotkey",
                        "feedback_type": "mode",
                        "global_x": 512,
                        "global_y": 288,
                    }
                ]
            )
        )

        window._refresh_shortcut_feedback_overlay()
        window._refresh_shortcut_feedback_overlay()

        self.assertEqual(fake_overlay.show_calls, [("Hotkey", 512, 288)])
        window.close()

    def test_tracking_stopped_hides_shortcut_feedback_overlay(self):
        window = _TestableMainWindow(ui_mode="prod")
        current_tracker = _FakeTracker()
        fake_overlay = _FakeShortcutFeedbackOverlay()
        window.hand_tracker = current_tracker
        window.shortcut_feedback_overlay = fake_overlay
        window._test_sender = current_tracker

        window.on_tracking_stopped()

        self.assertEqual(fake_overlay.hide_calls, 1)

    def test_macos_authorized_preflight_starts_tracking(self):
        window = _TestableMainWindow(ui_mode="prod")
        tracker = _FakeStartTracker(start_result=True)
        window.hand_tracker = tracker

        with patch("frontend.main_window.platform.system", return_value="Darwin"), patch(
            "frontend.main_window.get_camera_permission_status",
            return_value="authorized",
        ):
            started = window.ensure_tracking_running()

        self.assertTrue(started)
        self.assertEqual(len(tracker.start_calls), 1)
        self.assertEqual(window.status_label.text(), "Status: Starting...")
        self.assertEqual(window.start_button.text(), "Stop Tracking")
        window.close()

    def test_macos_denied_preflight_blocks_tracking(self):
        window = _TestableMainWindow(ui_mode="prod")
        tracker = _FakeStartTracker(start_result=True)
        window.hand_tracker = tracker

        with patch("frontend.main_window.platform.system", return_value="Darwin"), patch(
            "frontend.main_window.get_camera_permission_status",
            return_value="denied",
        ):
            started = window.ensure_tracking_running()

        self.assertFalse(started)
        self.assertEqual(tracker.start_calls, [])
        self.assertIn("Camera access denied.", window.status_label.text())
        self.assertEqual(window.start_button.text(), "Start Tracking")
        window.close()

    def test_macos_restricted_preflight_blocks_tracking(self):
        window = _TestableMainWindow(ui_mode="prod")
        tracker = _FakeStartTracker(start_result=True)
        window.hand_tracker = tracker

        with patch("frontend.main_window.platform.system", return_value="Darwin"), patch(
            "frontend.main_window.get_camera_permission_status",
            return_value="restricted",
        ):
            started = window.ensure_tracking_running()

        self.assertFalse(started)
        self.assertEqual(tracker.start_calls, [])
        self.assertIn("Camera access is restricted", window.status_label.text())
        self.assertEqual(window.start_button.text(), "Start Tracking")
        window.close()

    def test_macos_not_determined_requests_permission_then_starts(self):
        window = _TestableMainWindow(ui_mode="prod")
        tracker = _FakeStartTracker(start_result=True)
        window.hand_tracker = tracker
        callback_holder = {}

        def _request_permission(callback):
            callback_holder["callback"] = callback
            return True

        with patch("frontend.main_window.platform.system", return_value="Darwin"), patch(
            "frontend.main_window.get_camera_permission_status",
            side_effect=["not_determined", "authorized"],
        ), patch(
            "frontend.main_window.request_camera_permission",
            side_effect=_request_permission,
        ):
            started = window.ensure_tracking_running()
            self.assertFalse(started)
            self.assertEqual(window.status_label.text(), "Status: Waiting for camera permission...")
            self.assertEqual(tracker.start_calls, [])
            callback_holder["callback"](True)

        self.assertEqual(len(tracker.start_calls), 1)
        self.assertEqual(window.status_label.text(), "Status: Starting...")
        window.close()

    def test_tracking_error_normalizes_macos_camera_message(self):
        window = _TestableMainWindow(ui_mode="prod")
        current_tracker = _FakeTracker()
        window.hand_tracker = current_tracker
        window._test_sender = current_tracker

        window.on_tracking_error("Error occurred: Camera access denied by macOS permissions")

        self.assertIn("Camera access denied.", window.status_label.text())
        window.close()


if __name__ == "__main__":
    unittest.main()
