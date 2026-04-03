import time

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from frontend.widgets.settings.settings_theme import (
    animate_opacity,
    apply_app_theme,
    polish_widget,
)


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
        self._preview_state = "waiting"
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.preview_frame = QFrame()
        self.preview_frame.setProperty("appRole", "preview-shell")
        self.preview_frame.setProperty("appState", self._preview_state)
        frame_layout = QGridLayout(self.preview_frame)
        frame_layout.setContentsMargins(18, 18, 18, 18)

        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setScaledContents(False)
        self.video_label.setStyleSheet("background: transparent;")
        frame_layout.addWidget(self.video_label, 0, 0)

        self.overlay_card = QFrame()
        self.overlay_card.setProperty("appRole", "preview-overlay")
        overlay_layout = QVBoxLayout(self.overlay_card)
        overlay_layout.setContentsMargins(22, 18, 22, 18)
        overlay_layout.setSpacing(6)

        self.overlay_title = QLabel()
        self.overlay_title.setProperty("appPreviewRole", "overlay-title")
        self.overlay_title.setAlignment(Qt.AlignCenter)
        overlay_layout.addWidget(self.overlay_title)

        self.overlay_detail = QLabel()
        self.overlay_detail.setProperty("appPreviewRole", "overlay-detail")
        self.overlay_detail.setAlignment(Qt.AlignCenter)
        self.overlay_detail.setWordWrap(True)
        overlay_layout.addWidget(self.overlay_detail)

        frame_layout.addWidget(self.overlay_card, 0, 0, Qt.AlignCenter)
        layout.addWidget(self.preview_frame)

        apply_app_theme(self)
        self._show_status_message("Waiting on start", "Start tracking to view the live camera preview.")

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
            height, width, channels = frame.shape
            bytes_per_line = channels * width

            q_image = QImage(
                frame.data,
                width,
                height,
                bytes_per_line,
                QImage.Format_RGB888,
            )

            pixmap = QPixmap.fromImage(q_image)
            target_size = self.video_label.size()
            if pixmap.size() != target_size:
                scaled_pixmap = pixmap.scaled(
                    target_size,
                    Qt.KeepAspectRatio,
                    Qt.FastTransformation,
                )
            else:
                scaled_pixmap = pixmap

            self.video_label.setPixmap(scaled_pixmap)
            self._set_preview_state("active")
            self.overlay_card.hide()
        except Exception as e:
            print(f"Error updating frame: {e}")

    def clear_frame(self):
        """Clear the displayed frame and show a placeholder message."""
        self.video_label.clear()
        self._show_status_message("Waiting on start", "Start tracking to view the live camera preview.")

    def show_preview_hidden(self):
        """Show placeholder state while preview is disabled."""
        self.video_label.clear()
        self._show_status_message("Preview hidden", "Preview is paused. Tracking can continue in the background.")

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

    def _show_status_message(self, title: str, detail: str):
        """Show a centered status message in the preview area."""
        self.overlay_title.setText(title)
        self.overlay_detail.setText(detail)
        self.overlay_card.show()
        animate_opacity(self.overlay_card, start=0.0, end=1.0, duration=220)
        self._set_preview_state("hidden" if title == "Preview hidden" else "waiting")

    def _set_preview_state(self, state: str):
        if self._preview_state == state:
            return
        self._preview_state = state
        self.preview_frame.setProperty("appState", state)
        polish_widget(self.preview_frame)
