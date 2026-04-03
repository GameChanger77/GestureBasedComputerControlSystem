import os
import unittest
import numpy as np

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


if __name__ == "__main__":
    unittest.main()
