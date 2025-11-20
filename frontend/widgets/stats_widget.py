import time
from collections import deque
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Slot, Qt


class PerformanceStatsWidget(QWidget):
    """
    Widget for displaying performance statistics like FPS.
    """

    def __init__(self):
        super().__init__()
        self.frame_times = deque(maxlen=30)  # Track last 30 frame times
        self.last_frame_time = time.time()
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI components"""
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        # FPS label
        self.fps_label = QLabel("FPS: 0.0")
        self.fps_label.setStyleSheet("color: green; font-weight: bold;")
        layout.addWidget(self.fps_label)

        layout.addStretch()

        # Hands detected label
        self.hands_label = QLabel("Hands: 0")
        layout.addWidget(self.hands_label)

        layout.addStretch()

        self.setLayout(layout)

    def record_frame(self):
        """Record a frame for FPS calculation"""
        current_time = time.time()
        frame_time = current_time - self.last_frame_time
        self.last_frame_time = current_time

        self.frame_times.append(frame_time)

        # Calculate FPS
        if len(self.frame_times) > 0:
            avg_frame_time = sum(self.frame_times) / len(self.frame_times)
            fps = 1.0 / avg_frame_time if avg_frame_time > 0 else 0
            self.update_fps(fps)

    @Slot(float)
    def update_fps(self, fps: float):
        """
        Update the FPS display.

        Args:
            fps: Current FPS value
        """
        self.fps_label.setText(f"FPS: {fps:.1f}")

        # Change color based on performance
        if fps >= 25:
            self.fps_label.setStyleSheet("color: green; font-weight: bold;")
        elif fps >= 15:
            self.fps_label.setStyleSheet("color: orange; font-weight: bold;")
        else:
            self.fps_label.setStyleSheet("color: red; font-weight: bold;")

    @Slot(int)
    def update_hands_count(self, count: int):
        """
        Update the hands count display.

        Args:
            count: Number of hands detected
        """
        self.hands_label.setText(f"Hands: {count}")

    def reset(self):
        """Reset the stats"""
        self.frame_times.clear()
        self.fps_label.setText("FPS: 0.0")
        self.hands_label.setText("Hands: 0")
