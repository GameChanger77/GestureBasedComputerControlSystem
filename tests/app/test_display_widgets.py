import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from frontend.widgets.display.stats_widget import PerformanceStatsWidget
from frontend.widgets.display.video_widget import VideoWidget


class DisplayWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_video_widget_cycles_placeholder_states(self):
        widget = VideoWidget()

        self.assertEqual(widget.overlay_title.text(), "Waiting on start")

        widget.show_preview_hidden()
        self.assertEqual(widget.overlay_title.text(), "Preview hidden")
        self.assertEqual(widget.preview_frame.property("appState"), "hidden")

        widget.clear_frame()
        self.assertEqual(widget.overlay_title.text(), "Waiting on start")
        self.assertEqual(widget.preview_frame.property("appState"), "waiting")
        widget.close()

    def test_stats_widget_updates_and_resets_metric_cards(self):
        widget = PerformanceStatsWidget()

        widget.update_fps(31.5)
        widget.update_latency(42.4, 38.0, 75.5)
        widget.update_hands_count(2)
        widget.update_pipeline_breakdown(
            {
                "capture_ms": 8.1,
                "preprocess_ms": 3.2,
                "inference_wait_ms": 11.4,
                "hands_data_ms": 2.8,
                "strategize_ms": 1.7,
                "frame_pipeline_ms_avg": 28.4,
            }
        )

        self.assertEqual(widget.fps_card.value_label.text(), "31.5")
        self.assertEqual(widget.latency_card.value_label.text(), "42.4 ms")
        self.assertEqual(widget.hands_card.value_label.text(), "2")
        self.assertEqual(widget._pipeline_value_labels["capture_ms"].text(), "8.1 ms")
        self.assertEqual(widget._pipeline_value_labels["frame_pipeline_ms_avg"].text(), "28.4 ms")

        widget.reset()
        self.assertEqual(widget.fps_card.value_label.text(), "0.0")
        self.assertEqual(widget.latency_card.value_label.text(), "--")
        self.assertEqual(widget.hands_card.value_label.text(), "0")
        self.assertEqual(widget._pipeline_value_labels["capture_ms"].text(), "--")
        widget.close()


if __name__ == "__main__":
    unittest.main()
