from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import Slot, Qt
from PySide6.QtGui import QImage, QPixmap
import time


class VideoWidget(QWidget):
    """
    Widget for displaying camera video feed.
    Receives frames from HandTracker via signals and displays them.
    """

    def __init__(self):
        super().__init__()
        self.preview_enabled = True
        self._min_render_interval_ns = int(1_000_000_000 / 30)
        self._last_render_ns = 0
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI components"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Create label for displaying video
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setScaledContents(False)
        self.video_label.setStyleSheet(
            "background-color: black; color: white; font-size: 20px; font-weight: 600;"
        )
        self._show_status_message("Waiting on start")

        layout.addWidget(self.video_label)
        self.setLayout(layout)

    @Slot(object)
    def update_frame(self, frame):
        """
        Update the displayed frame.

        Args:
            frame: numpy array in RGB format
        """
        if not self.preview_enabled:
            return

        if frame is None or frame.size == 0:
            return

        if self._min_render_interval_ns > 0:
            now_ns = time.perf_counter_ns()
            if (now_ns - self._last_render_ns) < self._min_render_interval_ns:
                return
            self._last_render_ns = now_ns

        try:
            # Get frame dimensions
            height, width, channels = frame.shape

            # Calculate bytes per line
            bytes_per_line = channels * width

            # Create QImage from numpy array
            q_image = QImage(
                frame.data,
                width,
                height,
                bytes_per_line,
                QImage.Format_RGB888
            )

            # Convert to QPixmap
            pixmap = QPixmap.fromImage(q_image)

            target_size = self.video_label.size()
            if pixmap.size() != target_size:
                # Fast transform is significantly cheaper than smooth filtering for live preview.
                scaled_pixmap = pixmap.scaled(
                    target_size,
                    Qt.KeepAspectRatio,
                    Qt.FastTransformation
                )
            else:
                scaled_pixmap = pixmap

            # Display the pixmap
            self.video_label.setPixmap(scaled_pixmap)

        except Exception as e:
            print(f"Error updating frame: {e}")

    def clear_frame(self):
        """Clear the displayed frame and show a placeholder message."""
        self._show_status_message("Waiting on start")

    def show_preview_hidden(self):
        """Show placeholder state while preview is disabled."""
        self._show_status_message("Preview hidden")

    def set_preview_enabled(self, enabled: bool):
        """Enable or disable frame updates to the preview area."""
        self.preview_enabled = enabled
        if not enabled:
            self._last_render_ns = 0

    def set_max_preview_fps(self, max_fps: int):
        """Set preview render FPS cap without affecting backend tracking."""
        if max_fps <= 0:
            self._min_render_interval_ns = 0
        else:
            self._min_render_interval_ns = int(1_000_000_000 / max_fps)

    def _show_status_message(self, message: str):
        """Show a centered status message in the preview area."""
        self.video_label.clear()
        self.video_label.setText(message)
