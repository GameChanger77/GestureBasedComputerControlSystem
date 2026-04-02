from __future__ import annotations

import json
import math
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class TutorialAnimationWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = "move_mouse"
        self._progress = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._advance)
        self._timer.start()
        self.setMinimumHeight(240)

    def set_asset(self, asset_path: str | Path):
        path = Path(asset_path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {"scene": "move_mouse"}
        self._scene = str(payload.get("scene", "move_mouse"))
        self.update()

    def _advance(self):
        self._progress = (self._progress + 0.02) % 1.0
        self.update()

    def _draw_hand(
        self,
        painter: QPainter,
        x: float,
        y: float,
        *,
        fingers: dict[str, float] | None = None,
        thumb_curve: float = 0.0,
        pinch_target: tuple[float, float] | None = None,
    ):
        fingers = fingers or {
            "index": 0.9,
            "middle": 0.9,
            "ring": 0.9,
            "pinky": 0.9,
        }
        painter.save()
        painter.translate(x, y)
        palm = QColor("#53d8f4")
        edge = QColor("#b8f4ff")
        painter.setPen(QPen(edge, 2.0))
        painter.setBrush(palm)
        painter.drawRoundedRect(-18, -10, 36, 34, 12, 12)

        finger_specs = [
            ("index", -14),
            ("middle", -7),
            ("ring", 0),
            ("pinky", 7),
        ]
        finger_tips = {}
        for finger_name, offset in finger_specs:
            openness = max(0.12, min(1.0, float(fingers.get(finger_name, 0.2))))
            finger_height = 8 + (22 * openness)
            painter.drawRoundedRect(offset, -int(finger_height), 6, int(finger_height), 4, 4)
            finger_tips[finger_name] = (offset + 3, -finger_height)

        thumb_path = QPainterPath()
        thumb_path.moveTo(-18, 8)
        if pinch_target is None:
            thumb_path.cubicTo(-30, 2, -30, -2 + (thumb_curve * 8.0), -18 + (thumb_curve * 4.0), -18 + (thumb_curve * 3.0))
            thumb_tip = (-18 + (thumb_curve * 4.0), -18 + (thumb_curve * 3.0))
        else:
            target_x, target_y = pinch_target
            ctrl_x = -26 + ((target_x + 18) * 0.35)
            ctrl_y = 2 + ((target_y - 2) * 0.35)
            thumb_path.cubicTo(-30, 2, ctrl_x, ctrl_y, target_x, target_y)
            thumb_tip = (target_x, target_y)
        painter.drawPath(thumb_path)
        painter.setBrush(edge)
        painter.drawEllipse(int(thumb_tip[0] - 2), int(thumb_tip[1] - 2), 4, 4)
        for tip_x, tip_y in finger_tips.values():
            painter.drawEllipse(int(tip_x - 2), int(tip_y - 2), 4, 4)
        painter.restore()

    def _draw_cursor(self, painter: QPainter, x: float, y: float):
        painter.save()
        painter.translate(x, y)
        painter.setPen(QPen(QColor("#e8f5ff"), 2))
        painter.setBrush(QColor("#0ea5c6"))
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(0, 20)
        path.lineTo(6, 14)
        path.lineTo(12, 26)
        path.lineTo(16, 24)
        path.lineTo(10, 12)
        path.lineTo(18, 12)
        path.closeSubpath()
        painter.drawPath(path)
        painter.restore()

    def _finger_pose(self, *, index=0.2, middle=0.2, ring=0.2, pinky=0.2):
        return {
            "index": index,
            "middle": middle,
            "ring": ring,
            "pinky": pinky,
        }

    def paintEvent(self, event):
        _ = event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#091322"))

        width = float(self.width())
        height = float(self.height())
        frame_x = 24.0
        frame_y = 18.0
        frame_w = max(160.0, width - 48.0)
        frame_h = max(160.0, height - 36.0)

        painter.setPen(QPen(QColor("#28425f"), 1.5))
        painter.setBrush(QColor("#0d1a2c"))
        painter.drawRoundedRect(int(frame_x), int(frame_y), int(frame_w), int(frame_h), 20, 20)

        if self._scene == "move_mouse":
            target_x = frame_x + frame_w * 0.74
            target_y = frame_y + frame_h * 0.34
            painter.setPen(QPen(QColor("#7cf2aa"), 2))
            painter.setBrush(QColor("#133728"))
            painter.drawRoundedRect(int(target_x), int(target_y), 72, 72, 18, 18)
            hand_x = frame_x + frame_w * (0.26 + (0.38 * self._progress))
            self._draw_hand(
                painter,
                hand_x,
                frame_y + frame_h * 0.58,
                fingers=self._finger_pose(index=1.0, middle=0.18, ring=0.16, pinky=0.14),
                thumb_curve=0.2,
            )
            self._draw_cursor(painter, hand_x + 40, frame_y + frame_h * 0.46)
        elif self._scene in {"left_click", "right_click"}:
            button_x = frame_x + frame_w * 0.56
            button_y = frame_y + frame_h * 0.40
            accent = QColor("#0ea5c6" if self._scene == "left_click" else "#8b5cf6")
            painter.setPen(QPen(accent.lighter(130), 2))
            painter.setBrush(accent.darker(190))
            painter.drawRoundedRect(int(button_x), int(button_y), 120, 54, 18, 18)
            pinch_progress = max(0.0, min(1.0, (self._progress - 0.20) / 0.45))
            if self._scene == "left_click":
                middle_tip_y = -(8 + (22 * (1.0 - (0.78 * pinch_progress))))
                pinch_target = (-4 + (7 * pinch_progress), middle_tip_y + (5 * pinch_progress))
                fingers = self._finger_pose(index=0.92, middle=1.0 - (0.78 * pinch_progress), ring=0.18, pinky=0.15)
            else:
                ring_tip_y = -(8 + (22 * (1.0 - (0.78 * pinch_progress))))
                pinch_target = (3 + (3 * pinch_progress), ring_tip_y + (5 * pinch_progress))
                fingers = self._finger_pose(index=0.92, middle=0.18, ring=1.0 - (0.78 * pinch_progress), pinky=0.15)
            self._draw_hand(
                painter,
                frame_x + frame_w * 0.34,
                frame_y + frame_h * 0.58,
                fingers=fingers,
                pinch_target=pinch_target,
            )
            self._draw_cursor(painter, button_x + 26, button_y + 12)
        elif self._scene == "scroll":
            panel_x = frame_x + frame_w * 0.26
            panel_y = frame_y + frame_h * 0.24
            panel_w = frame_w * 0.46
            panel_h = frame_h * 0.54
            painter.setPen(QPen(QColor("#37506d"), 1.5))
            painter.setBrush(QColor("#101b2c"))
            painter.drawRoundedRect(int(panel_x), int(panel_y), int(panel_w), int(panel_h), 16, 16)
            for row in range(5):
                y = panel_y + 20 + (row * 22)
                painter.setPen(QPen(QColor("#22374f"), 3))
                painter.drawLine(int(panel_x + 16), int(y), int(panel_x + panel_w - 36), int(y))
            bar_y = panel_y + 26 + (math.sin(self._progress * math.tau) * 28)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#0ea5c6"))
            painter.drawRoundedRect(int(panel_x + panel_w - 24), int(bar_y), 10, 42, 5, 5)
            hand_y = frame_y + frame_h * (0.64 + (0.12 * math.sin(self._progress * math.tau)))
            self._draw_hand(
                painter,
                frame_x + frame_w * 0.78,
                hand_y,
                fingers=self._finger_pose(index=1.0, middle=1.0, ring=0.16, pinky=0.14),
                thumb_curve=0.18,
            )
        elif self._scene in {"switch_to_keyboard", "switch_to_mouse"}:
            mouse_fill = QColor("#0ea5c6" if self._scene == "switch_to_mouse" and self._progress > 0.5 else "#112338")
            key_fill = QColor("#0ea5c6" if self._scene == "switch_to_keyboard" and self._progress > 0.5 else "#112338")
            for index, (label, fill) in enumerate((("Mouse", mouse_fill), ("Keyboard", key_fill))):
                x = frame_x + 38 + (index * 144)
                painter.setPen(QPen(QColor("#32506f"), 1.5))
                painter.setBrush(fill)
                painter.drawRoundedRect(int(x), int(frame_y + 60), 120, 54, 18, 18)
                painter.setPen(QPen(QColor("#eef8ff"), 1))
                painter.drawText(int(x), int(frame_y + 60), 120, 54, int(Qt.AlignCenter), label)
            hand_x = frame_x + (frame_w * (0.32 if self._scene == "switch_to_mouse" else 0.66))
            self._draw_hand(
                painter,
                hand_x,
                frame_y + frame_h * 0.68,
                fingers=self._finger_pose(
                    index=1.0 if self._scene == "switch_to_keyboard" else 0.18,
                    middle=1.0 if self._scene == "switch_to_keyboard" else 0.18,
                    ring=1.0 if self._scene == "switch_to_keyboard" else 0.18,
                    pinky=1.0 if self._scene == "switch_to_keyboard" else 0.18,
                ),
                thumb_curve=0.75 if self._scene == "switch_to_keyboard" else 0.08,
            )
        elif self._scene == "drag_keyboard":
            key_x = frame_x + frame_w * (0.18 + (0.24 * self._progress))
            key_y = frame_y + frame_h * 0.48
            painter.setPen(QPen(QColor("#32506f"), 1.5))
            painter.setBrush(QColor("#112338"))
            painter.drawRoundedRect(int(key_x), int(key_y), 220, 82, 18, 18)
            for row in range(2):
                for col in range(5):
                    painter.setBrush(QColor("#172b44"))
                    painter.drawRoundedRect(int(key_x + 18 + (col * 38)), int(key_y + 16 + (row * 28)), 28, 18, 6, 6)
            self._draw_hand(
                painter,
                key_x + 56,
                key_y - 18,
                fingers=self._finger_pose(index=1.0, middle=1.0, ring=1.0, pinky=1.0),
                thumb_curve=0.72,
            )
        elif self._scene in {"lock_keyboard", "unlock_keyboard"}:
            painter.setPen(QPen(QColor("#32506f"), 1.5))
            painter.setBrush(QColor("#112338"))
            painter.drawRoundedRect(int(frame_x + 70), int(frame_y + 90), 220, 82, 18, 18)
            transition = max(0.0, min(1.0, self._progress))
            if self._scene == "lock_keyboard":
                openness = max(0.16, 1.0 - (0.88 * transition))
                thumb_curve = max(0.08, 0.7 - (0.58 * transition))
            else:
                openness = min(1.0, 0.18 + (0.82 * transition))
                thumb_curve = min(0.72, 0.10 + (0.62 * transition))
            self._draw_hand(
                painter,
                frame_x + 170,
                frame_y + 78,
                fingers=self._finger_pose(index=openness, middle=openness, ring=openness, pinky=openness),
                thumb_curve=thumb_curve,
            )
            badge_fill = QColor("#7cf2aa" if self._scene == "unlock_keyboard" else "#f2c94c")
            painter.setPen(QPen(QColor("#dff6ff"), 1.5))
            painter.setBrush(badge_fill)
            painter.drawEllipse(int(frame_x + 250), int(frame_y + 52), 40, 40)
        elif self._scene == "type_keyboard":
            painter.setPen(QPen(QColor("#32506f"), 1.5))
            painter.setBrush(QColor("#112338"))
            painter.drawRoundedRect(int(frame_x + 60), int(frame_y + 110), 260, 88, 18, 18)
            letters = ["h", "e", "l", "l", "o"]
            active_count = max(1, int(self._progress * len(letters)) + 1)
            for index, letter in enumerate(letters):
                x = frame_x + 78 + (index * 42)
                painter.setBrush(QColor("#0ea5c6") if index < active_count else QColor("#172b44"))
                painter.drawRoundedRect(int(x), int(frame_y + 130), 30, 28, 8, 8)
                painter.setPen(QPen(QColor("#eef8ff"), 1))
                painter.drawText(int(x), int(frame_y + 130), 30, 28, int(Qt.AlignCenter), letter)
            painter.setPen(QPen(QColor("#7cf2aa"), 2))
            painter.drawText(int(frame_x + 78), int(frame_y + 86), 220, 24, int(Qt.AlignLeft | Qt.AlignVCenter), "".join(letters[:active_count]))
            hover_x = frame_x + 92 + ((active_count - 1) * 42)
            hover_y = frame_y + 144
            painter.setPen(QPen(QColor("#7cf2aa"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(int(hover_x - 6), int(hover_y - 20), 42, 42, 10, 10)
            self._draw_hand(
                painter,
                frame_x + 154,
                frame_y + 90,
                fingers=self._finger_pose(index=0.98, middle=0.28, ring=0.20, pinky=0.18),
                thumb_curve=0.24,
            )
            self._draw_cursor(painter, hover_x + 6, hover_y - 10)
