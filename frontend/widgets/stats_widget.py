from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QVBoxLayout
from PySide6.QtCore import Slot


class PerformanceStatsWidget(QWidget):
    """Widget for displaying performance statistics (FPS, latency, hand count)."""

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        """Initialize UI components."""
        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(5, 5, 5, 5)
        root_layout.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)

        self.fps_label = QLabel('FPS: 0.0')
        self.fps_label.setStyleSheet('color: red; font-weight: bold;')
        top_row.addWidget(self.fps_label)

        top_row.addStretch()

        self.latency_label = QLabel('Latency: --')
        self.latency_label.setStyleSheet('color: gray; font-weight: bold;')
        top_row.addWidget(self.latency_label)

        top_row.addStretch()

        self.hands_label = QLabel('Hands: 0')
        top_row.addWidget(self.hands_label)

        top_row.addStretch()

        self.pipeline_breakdown_label = QLabel(
            'Stages (ms): cap -- | prep -- | infer -- | hands -- | strat -- | loop --'
        )
        self.pipeline_breakdown_label.setStyleSheet('color: #333;')

        root_layout.addLayout(top_row)
        root_layout.addWidget(self.pipeline_breakdown_label)

        self.setLayout(root_layout)

    def record_frame(self):
        """No-op compatibility shim; FPS comes from backend pipeline metrics."""
        return

    @Slot(float)
    def update_fps(self, fps: float):
        """Update pipeline FPS display."""
        self.fps_label.setText(f'FPS: {fps:.1f}')

        # Target band is 30-60 FPS.
        if fps >= 30:
            self.fps_label.setStyleSheet('color: green; font-weight: bold;')
        elif fps >= 24:
            self.fps_label.setStyleSheet('color: orange; font-weight: bold;')
        else:
            self.fps_label.setStyleSheet('color: red; font-weight: bold;')

    @Slot(object, object, object)
    def update_latency(self, avg_ms, latest_ms, p95_ms):
        """Update action latency display from rolling backend metrics."""
        if avg_ms is None or latest_ms is None or p95_ms is None:
            self.latency_label.setText('Latency: --')
            self.latency_label.setStyleSheet('color: gray; font-weight: bold;')
            return

        self.latency_label.setText(
            f'Latency: {avg_ms:.1f} ms (latest {latest_ms:.1f} ms, p95 {p95_ms:.1f} ms)'
        )

        if p95_ms <= 100:
            self.latency_label.setStyleSheet('color: green; font-weight: bold;')
        elif p95_ms <= 130:
            self.latency_label.setStyleSheet('color: orange; font-weight: bold;')
        else:
            self.latency_label.setStyleSheet('color: red; font-weight: bold;')

    @Slot(int)
    def update_hands_count(self, count: int):
        """Update detected hand count display."""
        self.hands_label.setText(f'Hands: {count}')

    @Slot(object)
    def update_pipeline_breakdown(self, metrics):
        """Update per-stage pipeline timing breakdown in milliseconds."""
        if not metrics:
            self.pipeline_breakdown_label.setText(
                'Stages (ms): cap -- | prep -- | infer -- | hands -- | strat -- | loop --'
            )
            return

        capture_ms = metrics.get('capture_ms')
        preprocess_ms = metrics.get('preprocess_ms')
        inference_ms = metrics.get('inference_wait_ms')
        hands_data_ms = metrics.get('hands_data_ms')
        strategize_ms = metrics.get('strategize_ms')
        loop_ms = metrics.get('frame_pipeline_ms_avg')

        def fmt(value):
            return '--' if value is None else f'{float(value):.1f}'

        self.pipeline_breakdown_label.setText(
            f'Stages (ms): cap {fmt(capture_ms)} | prep {fmt(preprocess_ms)} | '
            f'infer {fmt(inference_ms)} | hands {fmt(hands_data_ms)} | '
            f'strat {fmt(strategize_ms)} | loop {fmt(loop_ms)}'
        )

    def reset(self):
        """Reset stats display."""
        self.fps_label.setText('FPS: 0.0')
        self.fps_label.setStyleSheet('color: red; font-weight: bold;')
        self.latency_label.setText('Latency: --')
        self.latency_label.setStyleSheet('color: gray; font-weight: bold;')
        self.hands_label.setText('Hands: 0')
        self.pipeline_breakdown_label.setText(
            'Stages (ms): cap -- | prep -- | infer -- | hands -- | strat -- | loop --'
        )
