from PySide6.QtCore import Slot
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.widgets.settings.settings_theme import (
    MetricCard,
    SettingsCard,
    apply_app_theme,
    polish_widget,
    set_label_role,
    set_label_tone,
)


class PerformanceStatsWidget(QWidget):
    """Widget for displaying performance statistics (FPS, latency, hand count)."""

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        """Initialize UI components."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(14)

        metrics_row = QHBoxLayout()
        metrics_row.setContentsMargins(0, 0, 0, 0)
        metrics_row.setSpacing(12)

        self.fps_card = MetricCard("Pipeline FPS", "0.0", "Targeting stable real-time tracking.")
        self.latency_card = MetricCard("Action Latency", "--", "Rolling average, latest response, and p95.")
        self.hands_card = MetricCard("Hands Detected", "0", "Live count of tracked hands.")

        metrics_row.addWidget(self.fps_card, 1)
        metrics_row.addWidget(self.latency_card, 1)
        metrics_row.addWidget(self.hands_card, 1)
        root_layout.addLayout(metrics_row)

        self.pipeline_card = SettingsCard(surface="subtle-card")
        self.pipeline_card.setProperty("appRole", "metric-card")
        pipeline_title = QLabel("Pipeline Breakdown")
        set_label_role(pipeline_title, "metric-caption")
        self.pipeline_card.body_layout.addWidget(pipeline_title)

        pipeline_detail = QLabel("Per-stage timing in milliseconds.")
        set_label_role(pipeline_detail, "status-detail")
        self.pipeline_card.body_layout.addWidget(pipeline_detail)

        self._pipeline_value_labels = {}
        stages = [
            ("capture_ms", "Capture"),
            ("preprocess_ms", "Preprocess"),
            ("inference_wait_ms", "Inference"),
            ("hands_data_ms", "Hands Data"),
            ("strategize_ms", "Strategizer"),
            ("frame_pipeline_ms_avg", "Loop Total"),
        ]
        grid = QGridLayout()
        grid.setContentsMargins(0, 8, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(14)

        for index, (metric_key, label_text) in enumerate(stages):
            stage_widget = QWidget()
            stage_layout = QVBoxLayout(stage_widget)
            stage_layout.setContentsMargins(0, 0, 0, 0)
            stage_layout.setSpacing(3)

            caption = QLabel(label_text)
            set_label_role(caption, "metric-caption")
            stage_layout.addWidget(caption)

            value_label = QLabel("--")
            set_label_role(value_label, "card-title")
            stage_layout.addWidget(value_label)

            self._pipeline_value_labels[metric_key] = value_label
            grid.addWidget(stage_widget, index // 3, index % 3)

        self.pipeline_card.body_layout.addLayout(grid)
        root_layout.addWidget(self.pipeline_card)

        apply_app_theme(self)

    def record_frame(self):
        """No-op compatibility shim; FPS comes from backend pipeline metrics."""
        return

    @Slot(float)
    def update_fps(self, fps: float):
        """Update pipeline FPS display."""
        tone = "success" if fps >= 30 else "warning" if fps >= 24 else "error"
        detail = "Healthy live tracking." if fps >= 30 else "Tracking is usable but under target." if fps >= 24 else "Tracking is below the target performance band."
        self.fps_card.set_value(f"{fps:.1f}", tone=tone)
        self.fps_card.set_detail(detail)

    @Slot(object, object, object)
    def update_latency(self, avg_ms, latest_ms, p95_ms):
        """Update action latency display from rolling backend metrics."""
        if avg_ms is None or latest_ms is None or p95_ms is None:
            self.latency_card.set_value("--")
            self.latency_card.set_detail("Rolling latency stats appear once actions begin.")
            return

        tone = "success" if p95_ms <= 100 else "warning" if p95_ms <= 130 else "error"
        self.latency_card.set_value(f"{avg_ms:.1f} ms", tone=tone)
        self.latency_card.set_detail(f"Latest {latest_ms:.1f} ms | p95 {p95_ms:.1f} ms")

    @Slot(int)
    def update_hands_count(self, count: int):
        """Update detected hand count display."""
        tone = "accent" if count else None
        detail = "Tracking live hand landmarks." if count else "No hands are currently detected."
        self.hands_card.set_value(str(count), tone=tone)
        self.hands_card.set_detail(detail)

    @Slot(object)
    def update_pipeline_breakdown(self, metrics):
        """Update per-stage pipeline timing breakdown in milliseconds."""
        if not metrics:
            self._set_pipeline_value_labels({})
            return

        self._set_pipeline_value_labels(metrics)

    def _set_pipeline_value_labels(self, metrics):
        def fmt(value):
            return "--" if value is None else f"{float(value):.1f} ms"

        loop_value = metrics.get("frame_pipeline_ms_avg")
        for metric_key, label in self._pipeline_value_labels.items():
            value = metrics.get(metric_key)
            label.setText(fmt(value))
            if value is None:
                label.setProperty("textTone", None)
                polish_widget(label)
            elif metric_key == "frame_pipeline_ms_avg":
                if float(value) <= 33.0:
                    set_label_tone(label, "success")
                elif float(value) <= 45.0:
                    set_label_tone(label, "warning")
                else:
                    set_label_tone(label, "error")
            elif loop_value is not None and float(value) > float(loop_value) * 0.45:
                set_label_tone(label, "warning")
            else:
                label.setProperty("textTone", None)
                polish_widget(label)

    def reset(self):
        """Reset stats display."""
        self.fps_card.set_value("0.0", tone="error")
        self.fps_card.set_detail("Targeting stable real-time tracking.")
        self.latency_card.set_value("--")
        self.latency_card.set_detail("Rolling average, latest response, and p95.")
        self.hands_card.set_value("0")
        self.hands_card.set_detail("Live count of tracked hands.")
        self._set_pipeline_value_labels({})
