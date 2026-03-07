import cv2
import time
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget
)
from PySide6.QtCore import Slot, Signal

from frontend.video_widget import VideoWidget
from frontend.widgets.stats_widget import PerformanceStatsWidget
from frontend.widgets.settings_panel import SettingsPanel
from backend.camera_devices import resolve_camera_selection


class MainWindow(QMainWindow):
    """
    Main application window for hand gesture control.
    Displays camera feed, controls, and statistics.
    """

    # Signal to pass frame to video widget (thread-safe marshalling)
    frame_ready = Signal(object)

    def __init__(self, ui_mode="dev", component_factory=None):
        super().__init__()
        self.setWindowTitle("Hand Gesture Control")
        self.setMinimumSize(800, 700)

        if ui_mode not in ("dev", "prod"):
            raise ValueError(f"Unsupported ui_mode '{ui_mode}'")

        self.ui_mode = ui_mode
        self.is_dev_mode = self.ui_mode == "dev"
        self.component_factory = component_factory

        # Component references (will be injected)
        self.hand_tracker = None
        self.strategizer = None
        self.action = None
        self.config = None

        # Display state
        self.display_enabled = self.is_dev_mode
        self.show_landmarks = False
        self._preview_interval_ns = int(1_000_000_000 / 30)
        self._last_preview_emit_ns = 0

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

        self.video_widget = None
        self.stats_widget = None
        self.toggle_display_button = None
        self.toggle_landmarks_button = None
        self.settings_button = None
        self.back_button = None
        self.status_label = None
        self.settings_status_label = None
        self.page_stack = None
        self.main_page = None
        self.settings_page = None

        # Start/Stop tracking button
        self.start_button = QPushButton("Start Tracking")
        self.start_button.setMinimumHeight(40)
        self.start_button.clicked.connect(self.toggle_tracking)
        self._set_start_button_running(False)

        # Settings panel
        self.settings_panel = SettingsPanel(ui_mode=self.ui_mode)
        self.settings_panel.settings_saved.connect(self.on_settings_saved)

        if self.is_dev_mode:
            self.page_stack = QStackedWidget()

            # Main tracking page
            self.main_page = QWidget()
            main_page_layout = QVBoxLayout()
            main_page_layout.setContentsMargins(0, 0, 0, 0)
            main_page_layout.setSpacing(10)

            self.video_widget = VideoWidget()
            main_page_layout.addWidget(self.video_widget)

            self.stats_widget = PerformanceStatsWidget()
            main_page_layout.addWidget(self.stats_widget)

            button_layout = QHBoxLayout()
            button_layout.setSpacing(10)
            button_layout.addWidget(self.start_button)

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

            self.toggle_landmarks_button = QPushButton("Show Landmarks")
            self.toggle_landmarks_button.setMinimumHeight(40)
            self.toggle_landmarks_button.clicked.connect(self.toggle_landmarks)
            self.toggle_landmarks_button.setStyleSheet("""
                QPushButton {
                    background-color: #607D8B;
                    color: white;
                    font-weight: bold;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #546E7A;
                }
            """)
            button_layout.addWidget(self.toggle_landmarks_button)

            self.settings_button = QPushButton("Settings")
            self.settings_button.setMinimumHeight(40)
            self.settings_button.clicked.connect(self.show_settings_page)
            self.settings_button.setStyleSheet("""
                QPushButton {
                    background-color: #455A64;
                    color: white;
                    font-weight: bold;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #37474F;
                }
            """)
            button_layout.addWidget(self.settings_button)

            self.status_label = QLabel("Status: Not started")
            self.status_label.setStyleSheet("font-weight: bold;")
            button_layout.addWidget(self.status_label)

            button_layout.addStretch()
            main_page_layout.addLayout(button_layout)
            self.main_page.setLayout(main_page_layout)

            # Settings page
            self.settings_page = QWidget()
            settings_page_layout = QVBoxLayout()
            settings_page_layout.setContentsMargins(0, 0, 0, 0)
            settings_page_layout.setSpacing(10)

            settings_header = QHBoxLayout()
            settings_header.setSpacing(10)
            self.back_button = QPushButton("Back")
            self.back_button.setMinimumHeight(40)
            self.back_button.clicked.connect(self.show_main_page)
            settings_header.addWidget(self.back_button)

            settings_title = QLabel("Settings")
            settings_title.setStyleSheet("font-size: 18px; font-weight: bold;")
            settings_header.addWidget(settings_title)
            settings_header.addStretch()
            settings_page_layout.addLayout(settings_header)

            self.settings_status_label = QLabel("Status: Not started")
            self.settings_status_label.setStyleSheet("font-weight: bold;")
            settings_page_layout.addWidget(self.settings_status_label)

            settings_page_layout.addWidget(self.settings_panel)
            self.settings_page.setLayout(settings_page_layout)

            self.page_stack.addWidget(self.main_page)
            self.page_stack.addWidget(self.settings_page)
            self.page_stack.setCurrentWidget(self.main_page)
            main_layout.addWidget(self.page_stack)
        else:
            button_layout = QHBoxLayout()
            button_layout.setSpacing(10)
            button_layout.addWidget(self.start_button)

            self.status_label = QLabel("Status: Not started")
            self.status_label.setStyleSheet("font-weight: bold;")
            button_layout.addWidget(self.status_label)
            button_layout.addStretch()

            main_layout.addLayout(button_layout)
            main_layout.addWidget(self.settings_panel)

        central_widget.setLayout(main_layout)

        # Connect internal frame signal to video widget
        if self.video_widget:
            self.frame_ready.connect(self.video_widget.update_frame)

    def set_component_factory(self, component_factory):
        """Set backend component factory used when settings are applied."""
        self.component_factory = component_factory

    def _disconnect_tracker_signals(self, tracker):
        """Disconnect tracker signals if currently connected."""
        if not tracker:
            return
        for signal, slot in [
            (tracker.landmarks_detected, self.on_landmarks_detected),
            (tracker.tracking_started, self.on_tracking_started),
            (tracker.tracking_stopped, self.on_tracking_stopped),
            (tracker.error_occurred, self.on_tracking_error),
        ]:
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    def _set_start_button_running(self, running: bool):
        """Update start/stop button text and color."""
        if running:
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
            return

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

    def _set_status_text(self, text: str):
        """Update status labels across active pages."""
        if self.status_label:
            self.status_label.setText(text)
        if self.settings_status_label:
            self.settings_status_label.setText(text)

    @Slot()
    def show_settings_page(self):
        """Show dev settings page."""
        if self.is_dev_mode and self.page_stack and self.settings_page:
            self.page_stack.setCurrentWidget(self.settings_page)

    @Slot()
    def show_main_page(self):
        """Return to dev main tracking page."""
        if self.is_dev_mode and self.page_stack and self.main_page:
            self.page_stack.setCurrentWidget(self.main_page)

    def set_components(self, hand_tracker, strategizer, action, config=None):
        """
        Inject backend components and connect signals.

        Args:
            hand_tracker: HandTracker instance
            strategizer: Strategizer instance
            action: Action instance
            config: GestureConfig instance (optional)
        """
        self._disconnect_tracker_signals(self.hand_tracker)

        self.hand_tracker = hand_tracker
        self.strategizer = strategizer
        self.action = action
        self.config = config

        if config is not None:
            self.settings_panel.load_from_config(config)
            if self.is_dev_mode:
                self.show_landmarks = bool(config.get('show_landmarks_default', False))
                preview_max_fps = int(config.get('preview_max_fps', 30))
                self._set_preview_max_fps(preview_max_fps)
                if self.video_widget:
                    self.video_widget.set_max_preview_fps(preview_max_fps)
                self._update_landmarks_button_text()

        # Connect to HandTracker signals
        if self.hand_tracker:
            self.hand_tracker.set_preview_enabled(self.display_enabled if self.is_dev_mode else False)
            self.hand_tracker.landmarks_detected.connect(self.on_landmarks_detected)
            self.hand_tracker.tracking_started.connect(self.on_tracking_started)
            self.hand_tracker.tracking_stopped.connect(self.on_tracking_stopped)
            self.hand_tracker.error_occurred.connect(self.on_tracking_error)

    @Slot()
    def toggle_tracking(self):
        """Toggle tracking on/off"""
        if not self.hand_tracker:
            self._set_status_text("Status: Error - No tracker")
            return

        if self.hand_tracker.isRunning():
            # Stop tracking
            self.hand_tracker.stop_tracking()
            self._set_start_button_running(False)
            self._set_status_text("Status: Stopped")
            if self.video_widget:
                self.video_widget.clear_frame()
            if self.stats_widget:
                self.stats_widget.reset()
        else:
            # Start tracking
            camera_index, camera_backend = self._get_selected_camera_selection()
            if self.hand_tracker.start_tracking(camera_index=camera_index, camera_backend=camera_backend):
                self._set_start_button_running(True)
                self._set_status_text("Status: Starting...")
            else:
                self._set_status_text("Status: Failed to start")

    @Slot()
    def toggle_display(self):
        """Toggle video preview on/off while preserving layout space."""
        if not self.is_dev_mode or not self.video_widget:
            return

        self.display_enabled = not self.display_enabled

        if self.display_enabled:
            self.toggle_display_button.setText("Hide Preview")
            self.video_widget.set_preview_enabled(True)
            if self.hand_tracker:
                self.hand_tracker.set_preview_enabled(True)
            self._last_preview_emit_ns = 0
            # Keep widget visible so layout spacing is preserved.
            if not self.hand_tracker or not self.hand_tracker.isRunning():
                self.video_widget.clear_frame()
        else:
            self.toggle_display_button.setText("Show Preview")
            self.video_widget.set_preview_enabled(False)
            if self.hand_tracker:
                self.hand_tracker.set_preview_enabled(False)
            self._last_preview_emit_ns = 0
            # Keep widget visible and show placeholder when preview is disabled.
            self.video_widget.show_preview_hidden()

    @Slot()
    def toggle_landmarks(self):
        """Toggle hand landmark overlay drawing on preview frames."""
        if not self.is_dev_mode or not self.toggle_landmarks_button:
            return
        self.show_landmarks = not self.show_landmarks
        self._update_landmarks_button_text()

    def _update_landmarks_button_text(self):
        """Update landmark toggle button text from current state."""
        if not self.toggle_landmarks_button:
            return
        if self.show_landmarks:
            self.toggle_landmarks_button.setText("Hide Landmarks")
        else:
            self.toggle_landmarks_button.setText("Show Landmarks")

    def _set_preview_max_fps(self, max_fps: int):
        """Set UI preview refresh cap without affecting backend tracking FPS."""
        if max_fps <= 0:
            self._preview_interval_ns = 0
        else:
            self._preview_interval_ns = int(1_000_000_000 / max_fps)

    def _get_selected_camera_selection(self):
        """Resolve saved camera config to the best current device selection."""
        if not self.config:
            return 0, 0

        selected_camera = resolve_camera_selection(
            camera_index=self.config.get("camera_index", 0),
            camera_backend=self.config.get("camera_backend", 0),
            camera_path=self.config.get("camera_device_path", ""),
            camera_name=self.config.get("camera_device_name", ""),
        )
        return selected_camera.index, selected_camera.backend

    @Slot(dict, object)
    def on_landmarks_detected(self, landmarks_data, frame):
        """
        Handle detected landmarks from HandTracker.

        Args:
            landmarks_data: Dictionary with landmark data
            frame: Camera frame as numpy array
        """
        if not self.is_dev_mode:
            return

        if not self.stats_widget:
            return

        # Update backend-reported pipeline metrics
        metrics = landmarks_data.get('metrics', {}) if landmarks_data else {}
        pipeline_fps = metrics.get('pipeline_fps')
        if pipeline_fps is not None:
            self.stats_widget.update_fps(float(pipeline_fps))
        self.stats_widget.update_latency(
            metrics.get('action_latency_avg_ms'),
            metrics.get('action_latency_latest_ms'),
            metrics.get('action_latency_p95_ms')
        )
        self.stats_widget.update_pipeline_breakdown(metrics)

        # Update hands count from smoothed data
        hands_count = 0
        if landmarks_data and 'smoothed_hands_data' in landmarks_data:
            smoothed_hands_data = landmarks_data['smoothed_hands_data']
            if smoothed_hands_data:
                if smoothed_hands_data.camera.has_left:
                    hands_count += 1
                if smoothed_hands_data.camera.has_right:
                    hands_count += 1
        self.stats_widget.update_hands_count(hands_count)

        # Only update preview if enabled and frame data was provided.
        if self.display_enabled and self.video_widget and frame is not None and frame.size != 0:
            now_ns = time.perf_counter_ns()
            if (
                self._preview_interval_ns > 0
                and (now_ns - self._last_preview_emit_ns) < self._preview_interval_ns
            ):
                return

            self._last_preview_emit_ns = now_ns

            display_frame = frame

            # Draw landmarks on a copy so tracker-owned frame buffers stay read-only on the UI thread.
            if self.show_landmarks and landmarks_data and 'smoothed_hands_data' in landmarks_data:
                display_frame = frame.copy()
                display_frame = self.draw_landmarks(display_frame, landmarks_data['smoothed_hands_data'])

            self.frame_ready.emit(display_frame)

    @Slot(dict)
    def on_settings_saved(self, values):
        """
        Persist new settings and rebuild backend components.

        If tracking is currently running, stop and restart automatically.
        """
        if not self.config:
            self._set_status_text("Status: Error - config unavailable")
            return

        was_running = bool(self.hand_tracker and self.hand_tracker.isRunning())

        try:
            for key, value in values.items():
                self.config.set(key, value)
            self.config.save()
        except Exception as exc:
            self._set_status_text(f"Status: Error saving settings - {exc}")
            return

        rebuilt = self._rebuild_backend_components(restart_tracking=was_running)
        if not rebuilt:
            return

        if was_running:
            self._set_status_text("Status: Restarting with new settings...")
        else:
            self._set_status_text("Status: Settings saved")
        self.show_main_page()

    def _rebuild_backend_components(self, restart_tracking: bool):
        """Recreate Action/Strategizer/HandTracker from the factory."""
        if self.component_factory is None:
            self._set_status_text("Status: Error - backend factory not configured")
            return False

        old_tracker = self.hand_tracker
        old_action = self.action

        if old_tracker and old_tracker.isRunning():
            old_tracker.stop_tracking()

        if old_action and hasattr(old_action, "close"):
            try:
                old_action.close()
            except Exception:
                pass

        try:
            components = self.component_factory()
            self.set_components(
                components["hand_tracker"],
                components["strategizer"],
                components["action"],
                config=components["config"],
            )
        except Exception as exc:
            self._set_status_text(f"Status: Error rebuilding backend - {exc}")
            return False

        if restart_tracking:
            camera_index, camera_backend = self._get_selected_camera_selection()
            if self.hand_tracker.start_tracking(camera_index=camera_index, camera_backend=camera_backend):
                self._set_start_button_running(True)
                return True

            self._set_start_button_running(False)
            self._set_status_text("Status: Error - failed to restart tracking")
            return False

        self._set_start_button_running(False)
        if self.video_widget:
            self.video_widget.clear_frame()
        if self.stats_widget:
            self.stats_widget.reset()
        return True

    def draw_landmarks(self, image, hands_data):
        """
        Draw hand landmarks and connections from smoothed HandsData.

        Args:
            image: OpenCV image array
            hands_data: HandsData object with smoothed landmarks

        Returns:
            Annotated image with landmarks drawn
        """
        if hands_data is None:
            return image

        height, width, _ = image.shape

        # Process both left and right hands
        for hand in [hands_data.camera.left, hands_data.camera.right]:
            if not hand.exists:
                continue

            # Build flat list of landmarks for connections
            # Order: wrist(0), thumb(1-4), index(5-8), middle(9-12), ring(13-16), pinky(17-20)
            landmark_points = []

            # Add wrist
            wrist = hand.wrist
            if wrist is not None:
                x = int(wrist[0] * width)
                y = int(wrist[1] * height)
                landmark_points.append((x, y))
            else:
                continue

            # Add all finger joints
            for finger in [hand.thumb, hand.index, hand.middle, hand.ring, hand.pinky]:
                for joint in finger.joints:
                    x = int(joint[0] * width)
                    y = int(joint[1] * height)
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
        self._set_status_text("Status: Running")

    @Slot()
    def on_tracking_stopped(self):
        """Handle tracking stopped signal"""
        self._set_status_text("Status: Stopped")
        self._set_start_button_running(False)
        if self.video_widget:
            self.video_widget.clear_frame()

    @Slot(str)
    def on_tracking_error(self, error_message):
        """Handle tracking error signal"""
        self._set_start_button_running(False)
        self._set_status_text(f"Status: Error - {error_message}")

    def closeEvent(self, event):
        """Handle window close event"""
        # Stop tracking when window closes
        if self.hand_tracker and self.hand_tracker.isRunning():
            self.hand_tracker.stop_tracking()
        if self.action and hasattr(self.action, 'close'):
            try:
                self.action.close()
            except Exception:
                pass
        event.accept()
