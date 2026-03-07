import cv2
import time
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget
)
from PySide6.QtCore import Slot, Signal
from PySide6.QtCore import QTimer

from frontend.video_widget import VideoWidget
from frontend.production_keyboard_window import ProductionKeyboardWindow
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
        self.production_keyboard_window = ProductionKeyboardWindow() if not self.is_dev_mode else None

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
        self._auto_start_requested = False

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
        self.mode_label = None
        self.keyboard_status_label = None
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

            self.mode_label = QLabel("Mode: MOUSE")
            self.mode_label.setStyleSheet("font-weight: bold; color: #4CAF50;")
            button_layout.addWidget(self.mode_label)

            button_layout.addStretch()
            main_page_layout.addLayout(button_layout)

            self.keyboard_status_label = QLabel("Keyboard: Inactive")
            self.keyboard_status_label.setStyleSheet("font-family: Consolas, monospace; color: #333;")
            main_page_layout.addWidget(self.keyboard_status_label)

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
            # Production settings shell (no camera preview/stats UI).
            prod_layout = QVBoxLayout()
            prod_layout.setContentsMargins(0, 0, 0, 0)
            prod_layout.setSpacing(10)

            header = QLabel("Production Settings")
            header.setStyleSheet("font-size: 18px; font-weight: bold;")
            prod_layout.addWidget(header)

            controls_layout = QHBoxLayout()
            controls_layout.setSpacing(10)
            controls_layout.addWidget(self.start_button)

            self.status_label = QLabel("Status: Not started")
            self.status_label.setStyleSheet("font-weight: bold;")
            controls_layout.addWidget(self.status_label)
            controls_layout.addStretch()
            prod_layout.addLayout(controls_layout)

            prod_layout.addWidget(self.settings_panel)
            main_layout.addLayout(prod_layout)

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

        if not self._auto_start_requested:
            self._auto_start_requested = True
            QTimer.singleShot(0, self._auto_start_tracking)

    def _auto_start_tracking(self):
        """Start tracking automatically once UI event loop is running."""
        if not self.hand_tracker:
            return
        if self.hand_tracker.isRunning():
            return
        self.toggle_tracking()

    def _get_camera_start_dimensions(self):
        """Get camera start dimensions from config, with safe defaults."""
        cam_w = 640
        cam_h = 480
        config_source = self.config
        if config_source is None and self.strategizer and hasattr(self.strategizer, "config"):
            config_source = self.strategizer.config
        if config_source is not None:
            cam_w = int(config_source.get("camera_width", cam_w))
            cam_h = int(config_source.get("camera_height", cam_h))
        return cam_w, cam_h

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
            cam_w, cam_h = self._get_camera_start_dimensions()
            if self.hand_tracker.start_tracking(
                camera_index=camera_index,
                width=cam_w,
                height=cam_h,
                camera_backend=camera_backend,
            ):
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
            overlay_data = self._get_keyboard_overlay_data()
            if self.production_keyboard_window:
                self.production_keyboard_window.set_overlay_data(overlay_data)
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
        self._update_mode_label()

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
            flip_preview = self._should_flip_preview()
            if flip_preview:
                display_frame = cv2.flip(display_frame, 1)

            # Draw landmarks on a copy so tracker-owned frame buffers stay read-only on the UI thread.
            if self.show_landmarks and landmarks_data and 'smoothed_hands_data' in landmarks_data:
                display_frame = display_frame.copy()
                display_frame = self.draw_landmarks(
                    display_frame,
                    landmarks_data['smoothed_hands_data'],
                    mirror_x=flip_preview,
                )

            overlay_data = self._get_keyboard_overlay_data()
            if overlay_data and overlay_data.get("enabled"):
                # Overlay drawing mutates pixels; draw on a copy to avoid races with tracker ring buffers.
                if not self.show_landmarks:
                    display_frame = display_frame.copy()
                display_frame = self.draw_keyboard_overlay(
                    display_frame,
                    overlay_data,
                    draw_drag_bounds=self.show_landmarks,
                )
                status = overlay_data.get("status", "Keyboard active")
                event_text = overlay_data.get("last_event", "")
                conf = overlay_data.get("press_confidence", 0.0)
                key_count = len(overlay_data.get("keys", []))
                if self.keyboard_status_label:
                    self.keyboard_status_label.setText(
                        f"Keyboard: {status} | Keys: {key_count} | Last: {event_text} | Conf: {conf:.2f}"
                    )
            else:
                if self.keyboard_status_label:
                    self.keyboard_status_label.setText("Keyboard: Inactive")

            self.frame_ready.emit(display_frame)

    def _get_keyboard_overlay_data(self):
        if self.strategizer and hasattr(self.strategizer, "get_keyboard_overlay_data"):
            return self.strategizer.get_keyboard_overlay_data()
        return None

    def _should_flip_preview(self):
        if self.strategizer and hasattr(self.strategizer, "config"):
            return bool(self.strategizer.config.get("preview_flip_horizontal", True))
        return True

    def _update_mode_label(self):
        if not self.mode_label:
            return

        mode_name = "UNKNOWN"
        if self.strategizer and hasattr(self.strategizer, "get_mode_name"):
            mode_name = self.strategizer.get_mode_name()
        elif self.strategizer and hasattr(self.strategizer, "current_mode"):
            mode_name = str(self.strategizer.current_mode).split(".")[-1].upper()

        self.mode_label.setText(f"Mode: {mode_name}")
        if mode_name == "KEYBOARD":
            self.mode_label.setStyleSheet("font-weight: bold; color: #e67e22;")
        elif mode_name == "MOUSE":
            self.mode_label.setStyleSheet("font-weight: bold; color: #4CAF50;")
        else:
            self.mode_label.setStyleSheet("font-weight: bold; color: #607D8B;")

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
        old_strategizer = self.strategizer

        if old_tracker and old_tracker.isRunning():
            old_tracker.stop_tracking()

        if old_strategizer and hasattr(old_strategizer, "shutdown"):
            try:
                old_strategizer.shutdown()
            except Exception:
                pass

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
            cam_w, cam_h = self._get_camera_start_dimensions()
            if self.hand_tracker.start_tracking(
                camera_index=camera_index,
                width=cam_w,
                height=cam_h,
                camera_backend=camera_backend,
            ):
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

    def draw_landmarks(self, image, hands_data, mirror_x=False):
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
                x_coord = 1.0 - wrist[0] if mirror_x else wrist[0]
                x = int(x_coord * width)
                y = int(wrist[1] * height)
                landmark_points.append((x, y))
            else:
                continue

            # Add all finger joints
            for finger in [hand.thumb, hand.index, hand.middle, hand.ring, hand.pinky]:
                for joint in finger.joints:
                    x_coord = 1.0 - joint[0] if mirror_x else joint[0]
                    x = int(x_coord * width)
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

    def draw_keyboard_overlay(self, image, overlay_data, draw_drag_bounds=False):
        """
        Draw keyboard key rectangles and hover/press states.
        """
        if overlay_data is None:
            return image

        height, width, _ = image.shape
        hovered = set(overlay_data.get("hovered_keys", []))
        pressed = set(overlay_data.get("pressed_keys", []))
        fill_overlay = image.copy()
        key_draw_data = []

        for key in overlay_data.get("keys", []):
            x1 = int(max(0, min(width - 1, key["x"] * width)))
            y1 = int(max(0, min(height - 1, key["y"] * height)))
            x2 = int(max(0, min(width - 1, (key["x"] + key["w"]) * width)))
            y2 = int(max(0, min(height - 1, (key["y"] + key["h"]) * height)))

            border_color = (230, 230, 230)
            fill_color = (80, 80, 80)
            thickness = 2
            if key["id"] in hovered:
                border_color = (10, 245, 255)
                fill_color = (40, 140, 210)
                thickness = 3
            if key["id"] in pressed:
                border_color = (110, 255, 110)
                fill_color = (35, 170, 35)
                thickness = 3

            if x2 > x1 and y2 > y1:
                cv2.rectangle(fill_overlay, (x1, y1), (x2, y2), fill_color, -1)
                key_draw_data.append((key, x1, y1, x2, y2, border_color, thickness))

        image = cv2.addWeighted(fill_overlay, 0.52, image, 0.48, 0)

        for key, x1, y1, x2, y2, border_color, thickness in key_draw_data:
            cv2.rectangle(image, (x1, y1), (x2, y2), border_color, thickness)
            key_w = x2 - x1
            key_h = y2 - y1
            if key_w < 10 or key_h < 10:
                continue

            label = key.get("label", "")
            if not label:
                continue

            font_scale = max(0.30, min(0.62, min(key_w / 42.0, key_h / 18.0)))
            text_thickness = 1 if font_scale < 0.5 else 2
            text_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, text_thickness)
            tx = x1 + max(1, (key_w - text_size[0]) // 2)
            ty = y1 + max(text_size[1] + 1, (key_h + text_size[1]) // 2 - 1)
            cv2.putText(
                image,
                label,
                (tx, ty),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (0, 0, 0),
                text_thickness + 1,
                cv2.LINE_AA,
            )
            cv2.putText(
                image,
                label,
                (tx, ty),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (245, 245, 245),
                text_thickness,
                cv2.LINE_AA,
            )

        suggestion_chips = overlay_data.get("suggestion_chips", [])
        if suggestion_chips:
            for chip in suggestion_chips:
                label = str(chip.get("text", "")).strip()
                if not label:
                    continue
                x1 = int(max(0, min(width - 1, chip["x"] * width)))
                y1 = int(max(0, min(height - 1, chip["y"] * height)))
                x2 = int(max(0, min(width - 1, (chip["x"] + chip["w"]) * width)))
                y2 = int(max(0, min(height - 1, (chip["y"] + chip["h"]) * height)))
                if x2 <= x1 or y2 <= y1:
                    continue

                hovered_chip = bool(chip.get("hovered", False))
                fill_color = (55, 95, 155) if hovered_chip else (60, 60, 60)
                border_color = (80, 250, 255) if hovered_chip else (215, 215, 215)
                cv2.rectangle(image, (x1, y1), (x2, y2), fill_color, -1)
                cv2.rectangle(image, (x1, y1), (x2, y2), border_color, 2)

                chip_w = x2 - x1
                chip_h = y2 - y1
                font_scale = max(0.36, min(0.60, min(chip_w / 56.0, chip_h / 20.0)))
                text_thickness = 1 if font_scale < 0.52 else 2
                text_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, text_thickness)
                tx = x1 + max(2, (chip_w - text_size[0]) // 2)
                ty = y1 + max(text_size[1] + 2, (chip_h + text_size[1]) // 2 - 1)
                cv2.putText(
                    image,
                    label,
                    (tx, ty),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale,
                    (0, 0, 0),
                    text_thickness + 1,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    image,
                    label,
                    (tx, ty),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale,
                    (250, 250, 250),
                    text_thickness,
                    cv2.LINE_AA,
                )

        if draw_drag_bounds:
            for bound in overlay_data.get("drag_bounds", []):
                x1 = int(max(0, min(width - 1, bound["x"] * width)))
                y1 = int(max(0, min(height - 1, bound["y"] * height)))
                x2 = int(max(0, min(width - 1, (bound["x"] + bound["w"]) * width)))
                y2 = int(max(0, min(height - 1, (bound["y"] + bound["h"]) * height)))
                if x2 <= x1 or y2 <= y1:
                    continue

                cv2.rectangle(image, (x1, y1), (x2, y2), (255, 80, 255), 2)
                label = f"{bound.get('side', '?')} drag"
                cv2.putText(
                    image,
                    label,
                    (x1 + 3, max(12, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (255, 80, 255),
                    1,
                    cv2.LINE_AA,
                )

            hud = overlay_data.get("debug_hud", {})
            if isinstance(hud, dict):
                pinch_value = hud.get("pinch_value", None)
                lost_frames = int(hud.get("lost_frames", 0))
                pinch_text = "Pinch: --"
                if pinch_value is not None:
                    pinch_text = f"Pinch: {float(pinch_value):.3f}"
                hud_lines = [pinch_text]
                if lost_frames > 0:
                    hud_lines.append(f"Lost frames: {lost_frames}")

                if hud_lines:
                    panel_x = 10
                    panel_y = 58
                    panel_w = 210
                    panel_h = 28 + (20 * len(hud_lines))
                    cv2.rectangle(image, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), (30, 30, 30), -1)
                    cv2.rectangle(image, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), (110, 255, 255), 1)
                    for idx, line in enumerate(hud_lines):
                        cv2.putText(
                            image,
                            line,
                            (panel_x + 8, panel_y + 22 + (idx * 20)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.50,
                            (235, 235, 235),
                            1,
                            cv2.LINE_AA,
                        )

        swipe_points = overlay_data.get("swipe_path_points", [])
        if swipe_points:
            pts = []
            for p in swipe_points:
                px = int(max(0, min(width - 1, p.get("x", 0.0) * width)))
                py = int(max(0, min(height - 1, p.get("y", 0.0) * height)))
                pts.append((px, py))
            if len(pts) >= 2:
                for i in range(1, len(pts)):
                    cv2.line(image, pts[i - 1], pts[i], (0, 215, 255), 2, cv2.LINE_AA)
            if pts:
                cv2.circle(image, pts[-1], 4, (0, 255, 255), -1)

        hover_point = overlay_data.get("hover_point")
        if isinstance(hover_point, dict):
            hx = int(max(0, min(width - 1, float(hover_point.get("x", 0.0)) * width)))
            hy = int(max(0, min(height - 1, float(hover_point.get("y", 0.0)) * height)))
            cv2.circle(image, (hx, hy), 5, (0, 0, 0), -1, cv2.LINE_AA)
            cv2.circle(image, (hx, hy), 4, (90, 255, 255), -1, cv2.LINE_AA)

        status = overlay_data.get("status", "")
        if status:
            cv2.putText(
                image,
                status,
                (10, 22),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )

        swipe_best = overlay_data.get("swipe_best", "")
        if swipe_best:
            swipe_conf = float(overlay_data.get("swipe_confidence", 0.0))
            swipe_label = f"Swipe: {swipe_best} ({swipe_conf:.2f})"
            cv2.putText(
                image,
                swipe_label,
                (10, 46),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 225, 255),
                2,
                cv2.LINE_AA,
            )

        return image

    @Slot()
    def on_tracking_started(self):
        """Handle tracking started signal"""
        self._set_status_text("Status: Running")
        self._update_mode_label()

    @Slot()
    def on_tracking_stopped(self):
        """Handle tracking stopped signal"""
        self._set_status_text("Status: Stopped")
        self._set_start_button_running(False)
        if self.video_widget:
            self.video_widget.clear_frame()
        if self.production_keyboard_window:
            self.production_keyboard_window.set_overlay_data(None)
        self._update_mode_label()

    @Slot(str)
    def on_tracking_error(self, error_message):
        """Handle tracking error signal"""
        self._set_start_button_running(False)
        self._set_status_text(f"Status: Error - {error_message}")
        if self.production_keyboard_window:
            self.production_keyboard_window.set_overlay_data(None)
        self._update_mode_label()

    def closeEvent(self, event):
        """Handle window close event"""
        # Stop tracking when window closes
        if self.production_keyboard_window:
            self.production_keyboard_window.close()
        if self.hand_tracker and self.hand_tracker.isRunning():
            self.hand_tracker.stop_tracking()
        if self.strategizer and hasattr(self.strategizer, "shutdown"):
            try:
                self.strategizer.shutdown()
            except Exception:
                pass
        if self.action and hasattr(self.action, "release_all_keys"):
            self.action.release_all_keys()
        if self.action and hasattr(self.action, 'close'):
            try:
                self.action.close()
            except Exception:
                pass
        event.accept()
