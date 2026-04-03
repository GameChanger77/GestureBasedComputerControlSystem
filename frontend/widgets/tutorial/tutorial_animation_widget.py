from __future__ import annotations

import json
import math
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from backend.GestureConfig import GestureConfig
from backend.gestures.keyboard_mode.KeyboardLayoutHelper import KeyboardLayoutHelper
from backend.gestures.keyboard_mode.KeyboardLayouts import KeyboardLayoutRegistry


class TutorialAnimationWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = "move_mouse"
        self._progress = 0.0
        self._keyboard_layout_id = "qwerty"
        self._typing_rows = []
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
        if self._scene == "type_keyboard":
            self._refresh_typing_layout()
        self.update()

    def _advance(self):
        self._progress = (self._progress + 0.02) % 1.0
        self.update()

    def _refresh_typing_layout(self):
        self._keyboard_layout_id = self._resolve_keyboard_layout_id()
        self._typing_rows = KeyboardLayoutHelper.build_unified_rows("Meta", self._keyboard_layout_id)

    def _resolve_keyboard_layout_id(self) -> str:
        config_path = GestureConfig.resolve_config_path()
        layout_id = GestureConfig.DEFAULT_CONFIG.get("keyboard_layout", "qwerty")
        try:
            payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                layout_id = str(payload.get("keyboard_layout", layout_id))
        except Exception:
            pass
        resolved = KeyboardLayoutRegistry.get(layout_id, "Meta")
        return resolved.layout_id

    def _typing_rows_for_layout(self):
        if not self._typing_rows:
            self._refresh_typing_layout()
        return self._typing_rows

    def _resolve_swipe_word_slots(self, word: str):
        rows = self._typing_rows_for_layout()
        slots_by_token = {}
        for row in rows:
            for slot in row:
                token = slot.get("swipe_token")
                if token:
                    slots_by_token[str(token)] = slot
        matched = []
        for char in word.lower():
            slot = slots_by_token.get(char)
            if slot is None:
                return []
            matched.append(slot)
        return matched

    def _build_compact_keyboard_geometry(self, frame_x: float, frame_y: float, frame_w: float, frame_h: float):
        rows = self._typing_rows_for_layout()
        keyboard_x = frame_x + 34.0
        keyboard_y = frame_y + (frame_h * 0.48)
        keyboard_w = max(240.0, frame_w - 68.0)
        keyboard_h = max(86.0, frame_h * 0.38)
        row_gap = 6.0
        horizontal_gap = 4.0
        max_units = max(sum(float(slot.get("w", 1.0)) for slot in row) for row in rows)
        max_slot_count = max(len(row) for row in rows)
        unit_width = (keyboard_w - (horizontal_gap * (max_slot_count - 1))) / max_units
        key_height = (keyboard_h - (row_gap * (len(rows) - 1))) / max(1, len(rows))

        rendered_slots = []
        for row_index, row in enumerate(rows):
            row_units = sum(float(slot.get("w", 1.0)) for slot in row)
            row_width = (row_units * unit_width) + (horizontal_gap * max(0, len(row) - 1))
            row_x = keyboard_x + ((keyboard_w - row_width) / 2.0)
            cursor_x = row_x
            row_y = keyboard_y + (row_index * (key_height + row_gap))
            for slot in row:
                slot_width = float(slot.get("w", 1.0)) * unit_width
                rendered_slots.append(
                    {
                        "slot": slot,
                        "rect": (cursor_x, row_y, slot_width, key_height),
                        "center": (cursor_x + (slot_width / 2.0), row_y + (key_height / 2.0)),
                    }
                )
                cursor_x += slot_width + horizontal_gap
        return (keyboard_x, keyboard_y, keyboard_w, keyboard_h), rendered_slots

    def _typing_path_points(self, rendered_slots, word: str):
        centers_by_token = {}
        for rendered in rendered_slots:
            token = rendered["slot"].get("swipe_token")
            if token and str(token) not in centers_by_token:
                centers_by_token[str(token)] = rendered["center"]
        points = []
        for char in word.lower():
            center = centers_by_token.get(char)
            if center is None:
                return []
            points.append(center)
        return points

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
                fingers = self._finger_pose(
                    index=max(0.84, 1.0 - (0.12 * transition)),
                    middle=max(0.80, 0.96 - (0.10 * transition)),
                    ring=max(0.12, 0.20 - (0.04 * transition)),
                    pinky=max(0.10, 0.16 - (0.03 * transition)),
                )
                thumb_curve = max(0.58, 0.78 - (0.16 * transition))
            else:
                fingers = self._finger_pose(
                    index=min(1.0, 0.18 + (0.82 * transition)),
                    middle=min(1.0, 0.20 + (0.80 * transition)),
                    ring=min(1.0, 0.16 + (0.84 * transition)),
                    pinky=min(1.0, 0.14 + (0.86 * transition)),
                )
                thumb_curve = min(0.78, 0.10 + (0.68 * transition))
            self._draw_hand(
                painter,
                frame_x + 170,
                frame_y + 78,
                fingers=fingers,
                thumb_curve=thumb_curve,
            )
            badge_fill = QColor("#7cf2aa" if self._scene == "unlock_keyboard" else "#f2c94c")
            painter.setPen(QPen(QColor("#dff6ff"), 1.5))
            painter.setBrush(badge_fill)
            painter.drawEllipse(int(frame_x + 250), int(frame_y + 52), 40, 40)
        elif self._scene == "type_keyboard":
            keyboard_rect, rendered_slots = self._build_compact_keyboard_geometry(frame_x, frame_y, frame_w, frame_h)
            word = "hello"
            key_centers = self._typing_path_points(rendered_slots, word)
            highlighted_tokens = {char for char in word}

            painter.setPen(QPen(QColor("#32506f"), 1.5))
            painter.setBrush(QColor("#112338"))
            painter.drawRoundedRect(
                int(keyboard_rect[0]),
                int(keyboard_rect[1]),
                int(keyboard_rect[2]),
                int(keyboard_rect[3]),
                18,
                18,
            )
            for rendered in rendered_slots:
                slot = rendered["slot"]
                rect_x, rect_y, rect_w, rect_h = rendered["rect"]
                token = str(slot.get("swipe_token", ""))
                is_target = token in highlighted_tokens
                painter.setPen(QPen(QColor("#3d5876"), 1.0))
                painter.setBrush(QColor("#0b7e97") if is_target else QColor("#172b44"))
                painter.drawRoundedRect(int(rect_x), int(rect_y), int(rect_w), int(rect_h), 6, 6)
                painter.setPen(QPen(QColor("#eef8ff"), 1))
                painter.drawText(int(rect_x), int(rect_y), int(rect_w), int(rect_h), int(Qt.AlignCenter), str(slot["label"]))

            active_count = max(1, int(self._progress * len(word)) + 1)
            painter.setPen(QPen(QColor("#7cf2aa"), 2))
            painter.drawText(
                int(frame_x + 42),
                int(frame_y + 84),
                int(frame_w - 84),
                24,
                int(Qt.AlignLeft | Qt.AlignVCenter),
                word[:active_count].upper(),
            )

            if key_centers:
                path_points = [key_centers[0]]
                segment_count = max(1, len(key_centers) - 1)
                path_progress = min(0.999, self._progress) * segment_count
                segment_index = min(segment_count - 1, int(path_progress))
                segment_t = path_progress - segment_index
                for idx in range(1, segment_index + 1):
                    path_points.append(key_centers[idx])
                start_x, start_y = key_centers[segment_index]
                end_x, end_y = key_centers[min(segment_index + 1, len(key_centers) - 1)]
                hover_x = start_x + ((end_x - start_x) * segment_t)
                hover_y = start_y + ((end_y - start_y) * segment_t)
                path_points.append((hover_x, hover_y))

                swipe_pen = QPen(QColor("#7cf2aa"), 3)
                swipe_pen.setCapStyle(Qt.RoundCap)
                swipe_pen.setJoinStyle(Qt.RoundJoin)
                painter.setPen(swipe_pen)
                for idx in range(1, len(path_points)):
                    x1, y1 = path_points[idx - 1]
                    x2, y2 = path_points[idx]
                    painter.drawLine(int(x1), int(y1), int(x2), int(y2))

                painter.setPen(QPen(QColor("#e8f5ff"), 2))
                painter.setBrush(QColor("#0ea5c6"))
                painter.drawEllipse(int(hover_x - 7), int(hover_y - 7), 14, 14)
                painter.setPen(QPen(QColor("#7cf2aa"), 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(int(hover_x - 18), int(hover_y - 18), 36, 36, 12, 12)
            else:
                hover_x = frame_x + (frame_w * 0.5)
                hover_y = frame_y + (frame_h * 0.72)

            self._draw_hand(
                painter,
                hover_x - 42,
                hover_y - 38,
                fingers=self._finger_pose(index=0.76, middle=0.24, ring=0.20, pinky=0.18),
                pinch_target=(-1, -16),
            )
            self._draw_cursor(painter, hover_x + 10, hover_y - 14)
