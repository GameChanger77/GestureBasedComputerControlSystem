import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

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


if __name__ == "__main__":
    unittest.main()
