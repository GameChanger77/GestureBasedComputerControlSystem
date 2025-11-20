import cv2
import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel
)
from PySide6.QtCore import Slot, Signal

from frontend.video_widget import VideoWidget
from frontend.widgets.stats_widget import PerformanceStatsWidget


class MainWindow(QMainWindow):
    """
    Main application window for hand gesture control.
    Displays camera feed, controls, and statistics.
    """

    # Signal to pass frame to video widget (thread-safe marshalling)
    frame_ready = Signal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hand Gesture Control")
        self.setMinimumSize(800, 700)

        # Component references (will be injected)
        self.hand_tracker = None
        self.strategizer = None
        self.action = None

        # Display state
        self.display_enabled = True

        # Hand landmark connections (for drawing)
        self.HAND_CONNECTIONS = [
            # Thumb
            (0, 1), (1, 2), (2, 3), (3, 4),
            # Index finger
            (0, 5), (5, 6), (6, 7), (7, 8),
            # Middle finger
            (0, 9), (9, 10), (10, 11), (11, 12),
            # Ring finger
            (0, 13), (13, 14), (14, 15), (15, 16),
            # Pinky
            (0, 17), (17, 18), (18, 19), (19, 20)
        ]

        # Create UI
        self._create_ui()

    def _create_ui(self):
        """Create the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Video widget
        self.video_widget = VideoWidget()
        main_layout.addWidget(self.video_widget)

        # Stats widget
        self.stats_widget = PerformanceStatsWidget()
        main_layout.addWidget(self.stats_widget)

        # Control buttons layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # Start/Stop tracking button
        self.start_button = QPushButton("Start Tracking")
        self.start_button.setMinimumHeight(40)
        self.start_button.clicked.connect(self.toggle_tracking)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        button_layout.addWidget(self.start_button)

        # Toggle display button
        self.toggle_display_button = QPushButton("Hide Preview")
        self.toggle_display_button.setMinimumHeight(40)
        self.toggle_display_button.clicked.connect(self.toggle_display)
        self.toggle_display_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        button_layout.addWidget(self.toggle_display_button)

        # Status label
        self.status_label = QLabel("Status: Not started")
        self.status_label.setStyleSheet("font-weight: bold;")
        button_layout.addWidget(self.status_label)

        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        central_widget.setLayout(main_layout)

        # Connect internal frame signal to video widget
        self.frame_ready.connect(self.video_widget.update_frame)

    def set_components(self, hand_tracker, strategizer, action):
        """
        Inject backend components and connect signals.

        Args:
            hand_tracker: HandTracker instance
            strategizer: Strategizer instance
            action: Action instance
        """
        self.hand_tracker = hand_tracker
        self.strategizer = strategizer
        self.action = action

        # Connect to HandTracker signals
        if self.hand_tracker:
            self.hand_tracker.landmarks_detected.connect(self.on_landmarks_detected)
            self.hand_tracker.tracking_started.connect(self.on_tracking_started)
            self.hand_tracker.tracking_stopped.connect(self.on_tracking_stopped)
            self.hand_tracker.error_occurred.connect(self.on_tracking_error)

    @Slot()
    def toggle_tracking(self):
        """Toggle tracking on/off"""
        if not self.hand_tracker:
            self.status_label.setText("Status: Error - No tracker")
            return

        if self.hand_tracker.isRunning():
            # Stop tracking
            self.hand_tracker.stop_tracking()
            self.start_button.setText("Start Tracking")
            self.start_button.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    font-weight: bold;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
            """)
            self.status_label.setText("Status: Stopped")
            self.video_widget.clear_frame()
            self.stats_widget.reset()
        else:
            # Start tracking
            if self.hand_tracker.start_tracking(camera_index=0):
                self.start_button.setText("Stop Tracking")
                self.start_button.setStyleSheet("""
                    QPushButton {
                        background-color: #f44336;
                        color: white;
                        font-weight: bold;
                        border-radius: 5px;
                    }
                    QPushButton:hover {
                        background-color: #da190b;
                    }
                """)
                self.status_label.setText("Status: Starting...")
            else:
                self.status_label.setText("Status: Failed to start")

    @Slot()
    def toggle_display(self):
        """Toggle video display on/off (tracking continues)"""
        self.display_enabled = not self.display_enabled

        if self.display_enabled:
            self.toggle_display_button.setText("Hide Preview")
            self.video_widget.show()
        else:
            self.toggle_display_button.setText("Show Preview")
            self.video_widget.hide()

    @Slot(dict, object)
    def on_landmarks_detected(self, landmarks_data, frame):
        """
        Handle detected landmarks from HandTracker.

        Args:
            landmarks_data: Dictionary with landmark data
            frame: Camera frame as numpy array
        """
        if frame is None or frame.size == 0:
            return

        # Update stats (always, even if display is off)
        self.stats_widget.record_frame()

        # Update hands count
        hands_count = 0
        if landmarks_data and 'detection_result' in landmarks_data:
            detection_result = landmarks_data['detection_result']
            if detection_result and detection_result.hand_landmarks:
                hands_count = len(detection_result.hand_landmarks)
        self.stats_widget.update_hands_count(hands_count)

        # Only update display if enabled
        if self.display_enabled:
            # Draw landmarks on frame
            if landmarks_data and 'detection_result' in landmarks_data:
                frame = self.draw_landmarks(frame, landmarks_data['detection_result'])

            # Emit to video widget (thread-safe)
            self.frame_ready.emit(frame.copy())

    def draw_landmarks(self, image, detection_result):
        """
        Draw hand landmarks and connections on the image.

        Args:
            image: OpenCV image array
            detection_result: MediaPipe detection result

        Returns:
            Annotated image with landmarks drawn
        """
        if detection_result.hand_landmarks:
            for hand_landmarks in detection_result.hand_landmarks:
                # Convert normalized coordinates to pixel coordinates
                height, width, _ = image.shape
                landmark_points = []

                for landmark in hand_landmarks:
                    x = int(landmark.x * width)
                    y = int(landmark.y * height)
                    landmark_points.append((x, y))

                # Draw connections
                for connection in self.HAND_CONNECTIONS:
                    start_idx, end_idx = connection
                    if start_idx < len(landmark_points) and end_idx < len(landmark_points):
                        cv2.line(image, landmark_points[start_idx], landmark_points[end_idx],
                                 (0, 255, 0), 2)

                # Draw landmark points
                for i, point in enumerate(landmark_points):
                    # Different colors for different finger parts
                    if i == 0:  # Wrist
                        color = (255, 0, 0)  # Red
                        radius = 8
                    elif i in [4, 8, 12, 16, 20]:  # Fingertips
                        color = (0, 0, 255)  # Blue
                        radius = 6
                    else:  # Other joints
                        color = (255, 255, 0)  # Cyan
                        radius = 4

                    cv2.circle(image, point, radius, color, -1)

        return image

    @Slot()
    def on_tracking_started(self):
        """Handle tracking started signal"""
        self.status_label.setText("Status: Running")

    @Slot()
    def on_tracking_stopped(self):
        """Handle tracking stopped signal"""
        self.status_label.setText("Status: Stopped")
        self.start_button.setText("Start Tracking")

    @Slot(str)
    def on_tracking_error(self, error_message):
        """Handle tracking error signal"""
        self.status_label.setText(f"Status: Error - {error_message}")

    def closeEvent(self, event):
        """Handle window close event"""
        # Stop tracking when window closes
        if self.hand_tracker and self.hand_tracker.isRunning():
            self.hand_tracker.stop_tracking()
        event.accept()
