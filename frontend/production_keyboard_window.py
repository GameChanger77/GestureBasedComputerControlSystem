from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import QWidget

from backend.gestures.keyboard_mode.KeyboardThemes import KeyboardThemeRegistry


class ProductionKeyboardWindow(QWidget):
    def __init__(self):
        super().__init__()
        self._overlay_data: Dict[str, object] = {}
        self._window_rect_norm: Optional[Tuple[float, float, float, float]] = None
        self._content_rect: Tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)

        self.setWindowTitle("Swipe Keyboard")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWindowOpacity(0.0)
        self._opacity_animation: Optional[QPropertyAnimation] = None

    def _fade_to(self, opacity: float, duration: int = 180):
        if self._opacity_animation is not None:
            self._opacity_animation.stop()
        animation = QPropertyAnimation(self, b"windowOpacity", self)
        animation.setDuration(duration)
        animation.setStartValue(self.windowOpacity())
        animation.setEndValue(opacity)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._opacity_animation = animation
        animation.start()

    def set_overlay_data(self, overlay_data: Optional[Dict[str, object]]):
        if not overlay_data or not overlay_data.get("enabled") or overlay_data.get("surface") != "prod":
            self._overlay_data = {}
            self._window_rect_norm = None
            if self._opacity_animation is not None:
                self._opacity_animation.stop()
            self.setWindowOpacity(0.0)
            self.hide()
            return

        rect_px = overlay_data.get("prod_window_rect_px") or {}
        x = int(rect_px.get("x", 0))
        y = int(rect_px.get("y", 0))
        w = max(100, int(rect_px.get("w", 900)))
        h = max(80, int(rect_px.get("h", 300)))
        self.setGeometry(x, y, w, h)

        rect_norm = overlay_data.get("prod_window_rect_norm") or {}
        self._window_rect_norm = (
            float(rect_norm.get("x", 0.0)),
            float(rect_norm.get("y", 0.0)),
            max(1e-6, float(rect_norm.get("w", 1.0))),
            max(1e-6, float(rect_norm.get("h", 1.0))),
        )

        self._overlay_data = overlay_data
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
            self._fade_to(0.96, duration=190)
        self.update()

    def _to_local(self, nx: float, ny: float) -> Optional[Tuple[float, float]]:
        if self._window_rect_norm is None:
            return None
        rx, ry, rw, rh = self._window_rect_norm
        lx = (float(nx) - rx) / rw
        ly = (float(ny) - ry) / rh
        cx, cy, cw, ch = self._content_rect
        return (cx + (lx * cw), cy + (ly * ch))

    def _compute_content_rect(self) -> Tuple[float, float, float, float]:
        # Keep breathing room for an overhanging status badge at top-right.
        pad_left = 8.0
        pad_right = 24.0
        pad_top = 22.0
        pad_bottom = 8.0
        width = max(1.0, float(self.width()) - pad_left - pad_right)
        height = max(1.0, float(self.height()) - pad_top - pad_bottom)
        return (pad_left, pad_top, width, height)

    def _draw_lock_icon(self, painter: QPainter, locked: bool):
        palette = KeyboardThemeRegistry.get(self._overlay_data.get("theme_id", "dark"))
        badge_d = 32.0
        radius = badge_d / 2.0
        body_x, body_y, body_w, _ = self._content_rect
        # Overhang slightly above/right relative to keyboard body.
        cx = body_x + body_w + (radius * 0.35)
        cy = body_y - (radius * 0.35)
        # Constrain within widget paint area to avoid clipping.
        cx = max(radius + 1.0, min(float(self.width()) - radius - 1.0, cx))
        cy = max(radius + 1.0, min(float(self.height()) - radius - 1.0, cy))
        bx = cx - (badge_d / 2.0)
        by = cy - (badge_d / 2.0)

        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(*palette.badge_shadow)))
        painter.drawEllipse(int(bx) + 1, int(by) + 2, int(badge_d), int(badge_d))

        painter.setPen(QPen(QColor(*palette.badge_edge), 1.4))
        painter.setBrush(QBrush(QColor(*palette.badge_fill)))
        painter.drawEllipse(int(bx), int(by), int(badge_d), int(badge_d))

        body_w = int(badge_d * 0.42)
        body_h = int(badge_d * 0.30)
        body_x = int(cx - (body_w / 2.0))
        body_y = int(cy + (badge_d * 0.02))
        shackle_w = int(body_w * 0.95)
        shackle_h = int(body_h * 1.05)
        shackle_x = int(cx - (shackle_w / 2.0))
        shackle_y = int(body_y - (body_h * 0.92))

        shackle_color = QColor(*(palette.lock_shackle_locked if locked else palette.lock_shackle_unlocked))
        body_color = QColor(*(palette.lock_body_locked if locked else palette.lock_body_unlocked))
        painter.setPen(QPen(shackle_color, 2.0))
        painter.setBrush(Qt.NoBrush)
        if locked:
            painter.drawArc(shackle_x, shackle_y, shackle_w, shackle_h, 0 * 16, 180 * 16)
        else:
            painter.drawArc(shackle_x + 3, shackle_y, shackle_w, shackle_h, 18 * 16, 148 * 16)

        painter.setPen(QPen(QColor(53, 61, 74, 255), 1.1))
        painter.setBrush(QBrush(body_color))
        painter.drawRoundedRect(body_x, body_y, body_w, body_h, 3, 3)

    def paintEvent(self, event):
        _ = event
        if not self._overlay_data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self._content_rect = self._compute_content_rect()
        body_x, body_y, body_w, body_h = self._content_rect
        palette = KeyboardThemeRegistry.get(self._overlay_data.get("theme_id", "dark"))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(5, 10, 18, 86)))
        painter.drawRoundedRect(int(body_x + 6.0), int(body_y + 8.0), int(body_w), int(body_h), 16, 16)

        # Keyboard body
        bg = QColor(*palette.keyboard_body_fill)
        border = QColor(*palette.keyboard_body_edge)
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1.5))
        painter.drawRoundedRect(int(body_x), int(body_y), int(body_w), int(body_h), 14, 14)

        hovered = set(self._overlay_data.get("hovered_keys", []))
        pressed = set(self._overlay_data.get("pressed_keys", []))

        for key in self._overlay_data.get("keys", []):
            p1 = self._to_local(float(key.get("x", 0.0)), float(key.get("y", 0.0)))
            p2 = self._to_local(
                float(key.get("x", 0.0)) + float(key.get("w", 0.0)),
                float(key.get("y", 0.0)) + float(key.get("h", 0.0)),
            )
            if p1 is None or p2 is None:
                continue
            x1, y1 = p1
            x2, y2 = p2
            if x2 <= x1 or y2 <= y1:
                continue

            key_id = str(key.get("id", ""))
            if key_id in pressed:
                fill = QColor(*palette.key_pressed_fill)
                edge = QColor(*palette.key_pressed_edge)
            elif key_id in hovered:
                fill = QColor(*palette.key_hover_fill)
                edge = QColor(*palette.key_hover_edge)
            else:
                fill = QColor(*palette.key_fill)
                edge = QColor(*palette.key_edge)

            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(edge, 1.3))
            painter.drawRoundedRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1), 6, 6)

            label = str(key.get("label", ""))
            if label:
                painter.setPen(QPen(QColor(*palette.key_label), 1))
                painter.drawText(
                    int(x1),
                    int(y1),
                    int(x2 - x1),
                    int(y2 - y1),
                    int(Qt.AlignCenter),
                    label,
                )

        for chip in self._overlay_data.get("suggestion_chips", []):
            text = str(chip.get("text", "")).strip()
            if not text:
                continue
            p1 = self._to_local(float(chip.get("x", 0.0)), float(chip.get("y", 0.0)))
            p2 = self._to_local(
                float(chip.get("x", 0.0)) + float(chip.get("w", 0.0)),
                float(chip.get("y", 0.0)) + float(chip.get("h", 0.0)),
            )
            if p1 is None or p2 is None:
                continue
            x1, y1 = p1
            x2, y2 = p2
            if x2 <= x1 or y2 <= y1:
                continue

            hovered_chip = bool(chip.get("hovered", False))
            fill = QColor(*(palette.suggestion_hover_fill if hovered_chip else palette.suggestion_fill))
            edge = QColor(*(palette.suggestion_hover_edge if hovered_chip else palette.suggestion_edge))
            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(edge, 1.2))
            painter.drawRoundedRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1), 7, 7)
            painter.setPen(QPen(QColor(*palette.suggestion_label), 1))
            painter.drawText(int(x1), int(y1), int(x2 - x1), int(y2 - y1), int(Qt.AlignCenter), text)

        swipe_points = self._overlay_data.get("swipe_path_points", [])
        local_pts: List[Tuple[float, float]] = []
        for point in swipe_points:
            lp = self._to_local(float(point.get("x", 0.0)), float(point.get("y", 0.0)))
            if lp is None:
                continue
            local_pts.append(lp)

        if len(local_pts) >= 2:
            painter.setPen(QPen(QColor(*palette.swipe_path), 2.2))
            for idx in range(1, len(local_pts)):
                x1, y1 = local_pts[idx - 1]
                x2, y2 = local_pts[idx]
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        hover_point = self._overlay_data.get("hover_point")
        if isinstance(hover_point, dict):
            hp = self._to_local(float(hover_point.get("x", 0.0)), float(hover_point.get("y", 0.0)))
            if hp is not None:
                painter.setBrush(QBrush(QColor(*palette.hover_point_fill)))
                painter.setPen(QPen(QColor(*palette.hover_point_edge), 1.2))
                painter.drawEllipse(int(hp[0]) - 4, int(hp[1]) - 4, 8, 8)

        self._draw_lock_icon(painter, bool(self._overlay_data.get("prod_window_locked", True)))
