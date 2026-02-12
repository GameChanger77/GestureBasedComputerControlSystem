import cv2
import numpy as np
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import Slot, Qt
from PySide6.QtGui import QImage, QPixmap


class VideoWidget(QWidget):
    """
    Widget for displaying camera video feed.
    Receives frames from HandTracker via signals and displays them.
    """

    def __init__(self):
        super().__init__()
        self.preview_enabled = True
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
            frame: numpy array in BGR format from OpenCV
        """
        if not self.preview_enabled:
            return

        if frame is None or frame.size == 0:
            return

        try:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Get frame dimensions
            height, width, channels = rgb_frame.shape

            # Calculate bytes per line
            bytes_per_line = channels * width

            # Create QImage from numpy array
            q_image = QImage(
                rgb_frame.data,
                width,
                height,
                bytes_per_line,
                QImage.Format_RGB888
            )

            # Convert to QPixmap
            pixmap = QPixmap.fromImage(q_image)

            # Scale pixmap to label size while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                self.video_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

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

    def _show_status_message(self, message: str):
        """Show a centered status message in the preview area."""
        self.video_label.clear()
        self.video_label.setText(message)
