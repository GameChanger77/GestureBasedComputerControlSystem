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
        self.video_label.setStyleSheet("background-color: black;")
        self.video_label.setText("Waiting for camera...")

        layout.addWidget(self.video_label)
        self.setLayout(layout)

    @Slot(object)
    def update_frame(self, frame):
        """
        Update the displayed frame.

        Args:
            frame: numpy array in BGR format from OpenCV
        """
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
        """Clear the displayed frame"""
        self.video_label.clear()
        self.video_label.setText("Camera stopped")
