from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from frontend.widgets.settings.settings_theme import settings_font


class ShortcutFeedbackOverlay(QWidget):
    def __init__(self):
        super().__init__(None)
        self._text = ""
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_feedback)
        self._opacity_animation = QPropertyAnimation(self, b"windowOpacity", self)
        self._opacity_animation.setDuration(150)
        self._opacity_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._text_font = settings_font(size=15, weight=QFont.Weight.Bold)
        self._text_padding_x = 20
        self._text_padding_y = 12
        self._text_extra_width = 10
        self._cursor_offset_y = 26
        self._display_ms = 950

        self.setWindowTitle("Shortcut Feedback")
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
        )
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.hide()

    def show_shortcut(self, text: str, global_x: int, global_y: int):
        label = str(text or "").strip()
        if not label:
            return

        self._text = label
        self._reposition(int(global_x), int(global_y))
        self._hide_timer.stop()
        self._opacity_animation.stop()
        self.setWindowOpacity(0.30 if self.isVisible() else 0.0)
        self.show()
        self.raise_()
        self.update()
        self._opacity_animation.setStartValue(self.windowOpacity())
        self._opacity_animation.setEndValue(1.0)
        self._opacity_animation.start()
        self._hide_timer.start(self._display_ms)

    def hide_feedback(self):
        self._hide_timer.stop()
        self._opacity_animation.stop()
        self.hide()

    def _reposition(self, global_x: int, global_y: int):
        metrics = QFontMetrics(self._text_font)
        width = metrics.horizontalAdvance(self._text) + (self._text_padding_x * 2) + self._text_extra_width
        height = metrics.height() + (self._text_padding_y * 2)

        x = int(global_x - (width / 2))
        y = int(global_y + self._cursor_offset_y)

        screen = QApplication.screenAt(QPoint(global_x, global_y))
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is not None:
            geometry = screen.availableGeometry()
            x = max(geometry.left(), min(x, geometry.right() - width))
            y = max(geometry.top(), min(y, geometry.bottom() - height))

        self.setGeometry(x, y, width, height)

    def paintEvent(self, event):
        _ = event
        if not self._text:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        background = QColor(8, 18, 31, 224)
        border = QColor(61, 215, 247, 188)
        shadow = QColor(5, 10, 18, 220)
        text = QColor(174, 242, 255, 255)

        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(QPen(border, 1.4))
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 12, 12)

        painter.setFont(self._text_font)
        text_rect = rect.adjusted(self._text_padding_x, self._text_padding_y - 1, -self._text_padding_x, -self._text_padding_y)

        painter.setPen(shadow)
        painter.drawText(text_rect.translated(0, 1), int(Qt.AlignCenter), self._text)
        painter.setPen(text)
        painter.drawText(text_rect, int(Qt.AlignCenter), self._text)
