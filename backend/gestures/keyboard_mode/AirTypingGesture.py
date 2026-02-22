import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from backend.HandsData import HandsData
from backend.gestures.GestureRecognizer import GestureRecognizer


@dataclass
class HandFrame:
    left: float
    top: float
    width: float
    height: float


class AirTypingGesture(GestureRecognizer):
    """
    Keyboard overlay gesture for keyboard mode.

    This class is intentionally display-only:
    - draws and moves keyboard overlays
    - highlights hovered keys
    - does NOT emit key taps/presses/releases
    """

    def __init__(self, action, config, priority=15):
        super().__init__(action, priority=priority)
        self.config = config

        self.require_both_hands = bool(self.config.get("keyboard_require_both_hands", False))
        self.pause_on_hand_loss = bool(self.config.get("keyboard_pause_on_hand_loss", True))
        self.resume_stability_frames = int(self.config.get("keyboard_resume_stability_frames", 4))
        self.use_thumb_fingers = bool(self.config.get("keyboard_use_thumb_fingers", True))
        self.active_fingers = self.config.get("keyboard_active_fingers", ["index"])
        if not isinstance(self.active_fingers, list) or not self.active_fingers:
            self.active_fingers = ["index"]

        self.assign_hands_by_x = bool(self.config.get("keyboard_assign_hands_by_x", True))
        self.keyboard_split_layout = bool(self.config.get("keyboard_split_layout", False))
        self.single_hand_center_deadband = float(self.config.get("keyboard_single_hand_center_deadband", 0.08))
        self.flip_x_for_mapping = bool(
            self.config.get(
                "keyboard_flip_x_for_mapping",
                self.config.get("preview_flip_horizontal", True),
            )
        )

        # Hand-following keyboard geometry
        self.wrist_ema_alpha = float(self.config.get("keyboard_wrist_ema_alpha", 0.28))
        self.half_width_scale = float(self.config.get("keyboard_hand_half_width_scale", 3.2))
        self.half_width_min = float(self.config.get("keyboard_hand_half_width_min", 0.22))
        self.half_width_max = float(self.config.get("keyboard_hand_half_width_max", 0.40))
        self.half_height_ratio = float(self.config.get("keyboard_hand_height_ratio", 0.72))
        self.half_vertical_offset = float(self.config.get("keyboard_hand_vertical_offset", -0.015))
        self.half_horizontal_offset_left = float(self.config.get("keyboard_hand_horizontal_offset_left", 0.0))
        self.half_horizontal_offset_right = float(self.config.get("keyboard_hand_horizontal_offset_right", 0.0))
        self.half_vertical_offset_left = float(
            self.config.get("keyboard_hand_vertical_offset_left", self.half_vertical_offset)
        )
        self.half_vertical_offset_right = float(
            self.config.get("keyboard_hand_vertical_offset_right", self.half_vertical_offset)
        )
        self.finger_anchor_row = float(self.config.get("keyboard_finger_anchor_row", 0.20))
        self.finger_anchor_mix_x = float(self.config.get("keyboard_finger_anchor_mix_x", 0.92))
        self.finger_anchor_mix_y = float(self.config.get("keyboard_finger_anchor_mix_y", 0.90))
        self.drag_deadzone_margin_x = float(self.config.get("keyboard_drag_deadzone_margin_x", 0.14))
        self.drag_deadzone_margin_y = float(self.config.get("keyboard_drag_deadzone_margin_y", 0.18))
        self.size_ema_alpha = float(self.config.get("keyboard_hand_size_ema_alpha", 0.22))

        self._paused = True
        self._status = "Keyboard Initializing..."
        self._resume_counter = 0
        self._single_hand_side_hint: Optional[str] = None

        self._last_event = ""
        self._last_confidence = 0.0

        self._anchor_avg: Dict[str, Optional[Tuple[float, float]]] = {"left": None, "right": None}
        self._size_avg: Dict[str, Optional[Tuple[float, float]]] = {"left": None, "right": None}
        self._overlay_keys: List[Dict[str, object]] = []
        self._overlay_by_id: Dict[str, Dict[str, object]] = {}
        self._active_frames: Dict[str, Optional[HandFrame]] = {"left": None, "right": None}
        self._drag_bounds_by_side: Dict[str, HandFrame] = {}
        self._hovered_slots = set()

        self._rows_by_side = self._build_split_rows()
        self._rows_unified = self._build_unified_rows()

    def _slot(self, slot_id: str, label: str, key: str, width: float = 1.0) -> Dict[str, object]:
        return {"id": slot_id, "label": label, "key": key, "w": width}

    def _build_split_rows(self) -> Dict[str, List[List[Dict[str, object]]]]:
        left_rows = [
            [
                self._slot("backtick", "`", "backtick"),
                self._slot("1", "1", "1"),
                self._slot("2", "2", "2"),
                self._slot("3", "3", "3"),
                self._slot("4", "4", "4"),
                self._slot("5", "5", "5"),
            ],
            [
                self._slot("tab", "Tab", "tab", 1.4),
                self._slot("q", "Q", "q"),
                self._slot("w", "W", "w"),
                self._slot("e", "E", "e"),
                self._slot("r", "R", "r"),
                self._slot("t", "T", "t"),
            ],
            [
                self._slot("caps_lock", "Caps", "caps_lock", 1.7),
                self._slot("a", "A", "a"),
                self._slot("s", "S", "s"),
                self._slot("d", "D", "d"),
                self._slot("f", "F", "f"),
                self._slot("g", "G", "g"),
            ],
            [
                self._slot("left_shift", "Shift", "left_shift", 2.0),
                self._slot("z", "Z", "z"),
                self._slot("x", "X", "x"),
                self._slot("c", "C", "c"),
                self._slot("v", "V", "v"),
                self._slot("b", "B", "b"),
            ],
            [
                self._slot("left_ctrl", "Ctrl", "left_ctrl", 1.2),
                self._slot("left_win", "Win", "left_win", 1.1),
                self._slot("left_alt", "Alt", "left_alt", 1.1),
                self._slot("left_space", "Space", "space", 3.6),
            ],
        ]

        right_rows = [
            [
                self._slot("6", "6", "6"),
                self._slot("7", "7", "7"),
                self._slot("8", "8", "8"),
                self._slot("9", "9", "9"),
                self._slot("0", "0", "0"),
                self._slot("minus", "-", "minus"),
                self._slot("equals", "=", "equals"),
                self._slot("backspace", "Back", "backspace", 1.8),
            ],
            [
                self._slot("y", "Y", "y"),
                self._slot("u", "U", "u"),
                self._slot("i", "I", "i"),
                self._slot("o", "O", "o"),
                self._slot("p", "P", "p"),
                self._slot("left_bracket", "[", "left_bracket"),
                self._slot("right_bracket", "]", "right_bracket"),
                self._slot("backslash", "\\", "backslash"),
            ],
            [
                self._slot("h", "H", "h"),
                self._slot("j", "J", "j"),
                self._slot("k", "K", "k"),
                self._slot("l", "L", "l"),
                self._slot("semicolon", ";", "semicolon"),
                self._slot("quote", "'", "quote"),
                self._slot("enter", "Enter", "enter", 1.8),
            ],
            [
                self._slot("n", "N", "n"),
                self._slot("m", "M", "m"),
                self._slot("comma", ",", "comma"),
                self._slot("period", ".", "period"),
                self._slot("slash", "/", "slash"),
                self._slot("right_shift", "Shift", "right_shift", 1.8),
            ],
            [
                self._slot("right_space", "Space", "space", 3.6),
                self._slot("right_alt", "Alt", "right_alt", 1.1),
                self._slot("right_win", "Win", "right_win", 1.1),
                self._slot("right_ctrl", "Ctrl", "right_ctrl", 1.2),
            ],
        ]

        return {"left": left_rows, "right": right_rows}

    def _build_unified_rows(self) -> List[List[Dict[str, object]]]:
        return [
            [
                self._slot("backtick", "`", "backtick"),
                self._slot("1", "1", "1"),
                self._slot("2", "2", "2"),
                self._slot("3", "3", "3"),
                self._slot("4", "4", "4"),
                self._slot("5", "5", "5"),
                self._slot("6", "6", "6"),
                self._slot("7", "7", "7"),
                self._slot("8", "8", "8"),
                self._slot("9", "9", "9"),
                self._slot("0", "0", "0"),
                self._slot("minus", "-", "minus"),
                self._slot("equals", "=", "equals"),
                self._slot("backspace", "Back", "backspace", 1.8),
            ],
            [
                self._slot("tab", "Tab", "tab", 1.4),
                self._slot("q", "Q", "q"),
                self._slot("w", "W", "w"),
                self._slot("e", "E", "e"),
                self._slot("r", "R", "r"),
                self._slot("t", "T", "t"),
                self._slot("y", "Y", "y"),
                self._slot("u", "U", "u"),
                self._slot("i", "I", "i"),
                self._slot("o", "O", "o"),
                self._slot("p", "P", "p"),
                self._slot("left_bracket", "[", "left_bracket"),
                self._slot("right_bracket", "]", "right_bracket"),
                self._slot("backslash", "\\", "backslash"),
            ],
            [
                self._slot("caps_lock", "Caps", "caps_lock", 1.7),
                self._slot("a", "A", "a"),
                self._slot("s", "S", "s"),
                self._slot("d", "D", "d"),
                self._slot("f", "F", "f"),
                self._slot("g", "G", "g"),
                self._slot("h", "H", "h"),
                self._slot("j", "J", "j"),
                self._slot("k", "K", "k"),
                self._slot("l", "L", "l"),
                self._slot("semicolon", ";", "semicolon"),
                self._slot("quote", "'", "quote"),
                self._slot("enter", "Enter", "enter", 1.8),
            ],
            [
                self._slot("left_shift", "Shift", "left_shift", 2.0),
                self._slot("z", "Z", "z"),
                self._slot("x", "X", "x"),
                self._slot("c", "C", "c"),
                self._slot("v", "V", "v"),
                self._slot("b", "B", "b"),
                self._slot("n", "N", "n"),
                self._slot("m", "M", "m"),
                self._slot("comma", ",", "comma"),
                self._slot("period", ".", "period"),
                self._slot("slash", "/", "slash"),
                self._slot("right_shift", "Shift", "right_shift", 1.8),
            ],
            [
                self._slot("left_ctrl", "Ctrl", "left_ctrl", 1.2),
                self._slot("left_win", "Win", "left_win", 1.1),
                self._slot("left_alt", "Alt", "left_alt", 1.1),
                self._slot("space", "Space", "space", 6.5),
                self._slot("right_alt", "Alt", "right_alt", 1.1),
                self._slot("right_win", "Win", "right_win", 1.1),
                self._slot("right_ctrl", "Ctrl", "right_ctrl", 1.2),
            ],
        ]

    def _normalized_point(self, point: Optional[Tuple[float, float, float]]) -> Optional[Tuple[float, float, float]]:
        if point is None:
            return None
        x, y, z = point
        if self.flip_x_for_mapping:
            x = 1.0 - x
        return (x, y, z)

    @staticmethod
    def _distance(p1: Tuple[float, float, float], p2: Tuple[float, float, float]) -> float:
        dx = p1[0] - p2[0]
        dy = p1[1] - p2[1]
        dz = p1[2] - p2[2]
        return math.sqrt((dx * dx) + (dy * dy) + (dz * dz))

    @staticmethod
    def _clamp(value: float, min_value: float, max_value: float) -> float:
        return max(min_value, min(max_value, value))

    def _finger_names(self) -> List[str]:
        fingers = [f for f in self.active_fingers if f in {"thumb", "index", "middle", "ring", "pinky"}]
        if not fingers:
            fingers = ["index"]
        if self.use_thumb_fingers:
            if "thumb" not in fingers:
                fingers = ["thumb"] + fingers
        else:
            fingers = [f for f in fingers if f != "thumb"]
        return fingers

    def _get_hands_by_side(self, coord_space) -> Dict[str, object]:
        left = coord_space.left if coord_space.has_left else None
        right = coord_space.right if coord_space.has_right else None

        if not self.assign_hands_by_x:
            return {"left": left, "right": right}

        if left is None and right is None:
            return {"left": None, "right": None}

        # Single-hand fallback: keep one hand driving one side.
        if left is None or right is None:
            single = left if left is not None else right
            side_hint = self._single_hand_side_hint if self._single_hand_side_hint in {"left", "right"} else None
            side = side_hint

            wrist = self._normalized_point(single.wrist) if single is not None else None
            if wrist is not None:
                x = wrist[0]
                deadband = self._clamp(self.single_hand_center_deadband, 0.0, 0.25)
                if x < (0.5 - deadband):
                    side = "left"
                elif x > (0.5 + deadband):
                    side = "right"
                elif side is None:
                    side = "left" if x <= 0.5 else "right"

            if side is None:
                side = "left" if left is not None else "right"

            self._single_hand_side_hint = side
            return {"left": single if side == "left" else None, "right": single if side == "right" else None}

        self._single_hand_side_hint = None

        lw = self._normalized_point(left.wrist)
        rw = self._normalized_point(right.wrist)
        if lw is None or rw is None:
            return {"left": left, "right": right}

        if lw[0] <= rw[0]:
            return {"left": left, "right": right}
        return {"left": right, "right": left}

    def _get_tip(self, hand, finger_name: str) -> Optional[Tuple[float, float, float]]:
        if hand is None or not hand.exists:
            return None
        finger = getattr(hand, finger_name, None)
        if finger is None or finger.tip is None:
            return None
        return self._normalized_point(finger.tip)

    def _compute_hand_frame(self, side: str, hand) -> Optional[HandFrame]:
        if hand is None or not hand.exists or hand.wrist is None:
            return None

        wrist = self._normalized_point(hand.wrist)
        if wrist is None:
            return None

        fingertip_points = []
        for finger_name in ("index", "middle", "ring", "pinky"):
            tip = self._get_tip(hand, finger_name)
            if tip is not None:
                fingertip_points.append(tip)

        if fingertip_points:
            avg_tip_x = sum(p[0] for p in fingertip_points) / len(fingertip_points)
            avg_tip_y = sum(p[1] for p in fingertip_points) / len(fingertip_points)
            anchor_x_raw = (self.finger_anchor_mix_x * avg_tip_x) + ((1.0 - self.finger_anchor_mix_x) * wrist[0])
            anchor_y_raw = (self.finger_anchor_mix_y * avg_tip_y) + ((1.0 - self.finger_anchor_mix_y) * wrist[1])
        else:
            anchor_x_raw = wrist[0]
            anchor_y_raw = wrist[1]

        prev_anchor = self._anchor_avg.get(side)
        if prev_anchor is None:
            anchor_x = anchor_x_raw
            anchor_y = anchor_y_raw
        else:
            a = self.wrist_ema_alpha
            anchor_x = (prev_anchor[0] * (1.0 - a)) + (anchor_x_raw * a)
            anchor_y = (prev_anchor[1] * (1.0 - a)) + (anchor_y_raw * a)
        self._anchor_avg[side] = (anchor_x, anchor_y)

        index_base = self._normalized_point(hand.index.base)
        pinky_base = self._normalized_point(hand.pinky.base)
        span = 0.14
        if index_base is not None and pinky_base is not None:
            span = max(self._distance(index_base, pinky_base), 0.08)

        tip_span_x = 0.10
        if len(fingertip_points) >= 2:
            min_tip_x = min(p[0] for p in fingertip_points)
            max_tip_x = max(p[0] for p in fingertip_points)
            tip_span_x = max(0.06, max_tip_x - min_tip_x)

        finger_reach = 0.18
        if fingertip_points:
            finger_reach = max(
                0.12,
                sum(self._distance(tip, wrist) for tip in fingertip_points) / len(fingertip_points),
            )

        width_raw = max(
            span * self.half_width_scale,
            tip_span_x * 2.8,
            finger_reach * 1.35,
        )
        width = self._clamp(width_raw, self.half_width_min, self.half_width_max)
        height = self._clamp(width * self.half_height_ratio, 0.15, 0.55)

        prev_size = self._size_avg.get(side)
        if prev_size is not None:
            sa = self.size_ema_alpha
            width = (prev_size[0] * (1.0 - sa)) + (width * sa)
            height = (prev_size[1] * (1.0 - sa)) + (height * sa)
        self._size_avg[side] = (width, height)

        vertical_offset = self.half_vertical_offset_left if side == "left" else self.half_vertical_offset_right
        horizontal_offset = self.half_horizontal_offset_left if side == "left" else self.half_horizontal_offset_right

        top_raw = anchor_y - (height * self.finger_anchor_row) + vertical_offset
        center_x = self._clamp(anchor_x + horizontal_offset, width / 2.0, 1.0 - (width / 2.0))
        center_y = self._clamp(top_raw + (height / 2.0), height / 2.0, 1.0 - (height / 2.0))

        return HandFrame(
            left=center_x - (width / 2.0),
            top=center_y - (height / 2.0),
            width=width,
            height=height,
        )

    def _slot_from_uv(self, side: str, u: float, v: float) -> Optional[Dict[str, object]]:
        if u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0:
            return None

        rows = self._rows_by_side.get(side, []) if self.keyboard_split_layout else self._rows_unified
        if not rows:
            return None

        row_idx = min(len(rows) - 1, max(0, int(v * len(rows))))
        row = rows[row_idx]
        total_w = sum(float(slot["w"]) for slot in row)
        if total_w <= 1e-6:
            return None

        x_units = u * total_w
        accum = 0.0
        for slot in row:
            next_accum = accum + float(slot["w"])
            if x_units <= next_accum:
                return slot
            accum = next_accum
        return row[-1] if row else None

    def _map_tip_to_slot(self, side: str, tip: Tuple[float, float, float], frame: HandFrame) -> Optional[Dict[str, object]]:
        if frame.width <= 1e-6 or frame.height <= 1e-6:
            return None
        u = (tip[0] - frame.left) / frame.width
        v = (tip[1] - frame.top) / frame.height
        return self._slot_from_uv(side, u, v)

    def _build_overlay_keys(self, frames: Dict[str, Optional[HandFrame]]) -> List[Dict[str, object]]:
        if not self.keyboard_split_layout:
            frame = self._resolve_unified_frame(frames)
            if frame is None:
                return []

            rows = self._rows_unified
            if not rows:
                return []

            key_rects = []
            row_h = frame.height / len(rows)
            for row_idx, row in enumerate(rows):
                row_top = frame.top + (row_h * row_idx)
                row_total = sum(float(slot["w"]) for slot in row)
                if row_total <= 1e-6:
                    continue

                accum = 0.0
                for slot in row:
                    slot_w = float(slot["w"]) / row_total
                    x = frame.left + (frame.width * accum)
                    w = frame.width * slot_w
                    key_rects.append(
                        {
                            "id": str(slot["id"]),
                            "side": "full",
                            "label": str(slot["label"]),
                            "x": x,
                            "y": row_top,
                            "w": w,
                            "h": row_h,
                        }
                    )
                    accum += slot_w
            return key_rects

        key_rects = []
        for side in ("left", "right"):
            frame = frames.get(side)
            if frame is None:
                continue
            rows = self._rows_by_side[side]
            if not rows:
                continue

            row_h = frame.height / len(rows)
            for row_idx, row in enumerate(rows):
                row_top = frame.top + (row_h * row_idx)
                row_total = sum(float(slot["w"]) for slot in row)
                if row_total <= 1e-6:
                    continue

                accum = 0.0
                for slot in row:
                    slot_w = float(slot["w"]) / row_total
                    x = frame.left + (frame.width * accum)
                    w = frame.width * slot_w
                    key_rects.append(
                        {
                            "id": str(slot["id"]),
                            "side": side,
                            "label": str(slot["label"]),
                            "x": x,
                            "y": row_top,
                            "w": w,
                            "h": row_h,
                        }
                    )
                    accum += slot_w

        return key_rects

    def _resolve_unified_frame(self, frames: Dict[str, Optional[HandFrame]]) -> Optional[HandFrame]:
        left = frames.get("left")
        right = frames.get("right")

        if left is None and right is None:
            return None

        if left is not None and right is not None:
            left_edge = min(left.left, right.left)
            right_edge = max(left.left + left.width, right.left + right.width)
            width = self._clamp(right_edge - left_edge, 0.30, 0.95)
            center_x = self._clamp((left_edge + right_edge) / 2.0, width / 2.0, 1.0 - (width / 2.0))

            left_center_y = left.top + (left.height / 2.0)
            right_center_y = right.top + (right.height / 2.0)
            center_y = (left_center_y + right_center_y) / 2.0
            height = self._clamp(max(left.height, right.height), 0.15, 0.55)
            center_y = self._clamp(center_y, height / 2.0, 1.0 - (height / 2.0))

            return HandFrame(
                left=center_x - (width / 2.0),
                top=center_y - (height / 2.0),
                width=width,
                height=height,
            )

        source = left if left is not None else right
        source_center_x = source.left + (source.width / 2.0)
        source_center_y = source.top + (source.height / 2.0)
        width = self._clamp(source.width * 2.05, 0.30, 0.95)
        height = self._clamp(max(source.height, width * 0.34), 0.15, 0.55)
        center_x = self._clamp(source_center_x, width / 2.0, 1.0 - (width / 2.0))
        center_y = self._clamp(source_center_y, height / 2.0, 1.0 - (height / 2.0))
        return HandFrame(
            left=center_x - (width / 2.0),
            top=center_y - (height / 2.0),
            width=width,
            height=height,
        )

    def _set_overlay_keys(self, key_rects: List[Dict[str, object]]):
        self._overlay_keys = key_rects
        self._overlay_by_id = {str(key["id"]): key for key in key_rects}

    @staticmethod
    def _copy_frame(frame: Optional[HandFrame]) -> Optional[HandFrame]:
        if frame is None:
            return None
        return HandFrame(left=frame.left, top=frame.top, width=frame.width, height=frame.height)

    @staticmethod
    def _frame_center(frame: HandFrame) -> Tuple[float, float]:
        return (frame.left + (frame.width / 2.0), frame.top + (frame.height / 2.0))

    def _compute_deadzone_frame(self, frame: HandFrame) -> HandFrame:
        margin_x = max(0.0, frame.width * self.drag_deadzone_margin_x)
        margin_y = max(0.0, frame.height * self.drag_deadzone_margin_y)
        width = min(1.0, frame.width + (2.0 * margin_x))
        height = min(1.0, frame.height + (2.0 * margin_y))

        center_x, center_y = self._frame_center(frame)
        center_x = self._clamp(center_x, width / 2.0, 1.0 - (width / 2.0))
        center_y = self._clamp(center_y, height / 2.0, 1.0 - (height / 2.0))

        return HandFrame(
            left=center_x - (width / 2.0),
            top=center_y - (height / 2.0),
            width=width,
            height=height,
        )

    def _update_drag_bounds(self, frames: Dict[str, Optional[HandFrame]]):
        self._drag_bounds_by_side = {}
        if not self.keyboard_split_layout:
            unified_frame = self._resolve_unified_frame(frames)
            if unified_frame is not None:
                self._drag_bounds_by_side["full"] = self._compute_deadzone_frame(unified_frame)
            return

        for side in ("left", "right"):
            frame = frames.get(side)
            if frame is None:
                continue
            self._drag_bounds_by_side[side] = self._compute_deadzone_frame(frame)

    def _update_active_frames(
        self,
        candidate_frames: Dict[str, Optional[HandFrame]],
        recenter: bool,
    ):
        for side in ("left", "right"):
            candidate = candidate_frames.get(side)
            active = self._active_frames.get(side)

            if active is None and candidate is not None:
                self._active_frames[side] = self._copy_frame(candidate)
                continue

            if recenter:
                if candidate is not None:
                    self._active_frames[side] = self._copy_frame(candidate)
                continue

            if candidate is None or active is None:
                continue

            candidate_center_x, candidate_center_y = self._frame_center(candidate)
            deadzone = self._compute_deadzone_frame(active)
            deadzone_right = deadzone.left + deadzone.width
            deadzone_bottom = deadzone.top + deadzone.height

            shift_x = 0.0
            shift_y = 0.0
            if candidate_center_x < deadzone.left:
                shift_x = candidate_center_x - deadzone.left
            elif candidate_center_x > deadzone_right:
                shift_x = candidate_center_x - deadzone_right

            if candidate_center_y < deadzone.top:
                shift_y = candidate_center_y - deadzone.top
            elif candidate_center_y > deadzone_bottom:
                shift_y = candidate_center_y - deadzone_bottom

            if abs(shift_x) <= 1e-6 and abs(shift_y) <= 1e-6:
                continue

            active_center_x, active_center_y = self._frame_center(active)
            new_center_x = self._clamp(active_center_x + shift_x, active.width / 2.0, 1.0 - (active.width / 2.0))
            new_center_y = self._clamp(active_center_y + shift_y, active.height / 2.0, 1.0 - (active.height / 2.0))
            self._active_frames[side] = HandFrame(
                left=new_center_x - (active.width / 2.0),
                top=new_center_y - (active.height / 2.0),
                width=active.width,
                height=active.height,
            )

    def _fallback_overlay_frames(self) -> Dict[str, Optional[HandFrame]]:
        full_center_x = float(self.config.get("keyboard_fixed_center_x", 0.5))
        full_center_y = float(self.config.get("keyboard_fixed_center_y", 0.58))
        full_width = float(self.config.get("keyboard_fixed_width", 0.78))
        full_height = float(self.config.get("keyboard_fixed_height", 0.26))

        full_width = self._clamp(full_width, 0.35, 0.95)
        full_height = self._clamp(full_height, 0.12, 0.55)
        half_gap = max(0.01, full_width * 0.025)
        half_width = max(0.10, (full_width - half_gap) / 2.0)

        center_y = self._clamp(full_center_y, full_height / 2.0, 1.0 - (full_height / 2.0))
        left_center_x = self._clamp(
            full_center_x - ((half_width + half_gap) / 2.0),
            half_width / 2.0,
            1.0 - (half_width / 2.0),
        )
        right_center_x = self._clamp(
            full_center_x + ((half_width + half_gap) / 2.0),
            half_width / 2.0,
            1.0 - (half_width / 2.0),
        )

        return {
            "left": HandFrame(
                left=left_center_x - (half_width / 2.0),
                top=center_y - (full_height / 2.0),
                width=half_width,
                height=full_height,
            ),
            "right": HandFrame(
                left=right_center_x - (half_width / 2.0),
                top=center_y - (full_height / 2.0),
                width=half_width,
                height=full_height,
            ),
        }

    def _spread_overlay_frames(
        self,
        frames: Dict[str, Optional[HandFrame]],
    ) -> Dict[str, Optional[HandFrame]]:
        """Ensure overlay keeps two visible halves when frames collapse/overlap."""
        left = frames.get("left")
        right = frames.get("right")

        if left is None and right is None:
            return frames

        if left is not None and right is not None:
            left_cx = left.left + (left.width / 2.0)
            right_cx = right.left + (right.width / 2.0)
            avg_width = (left.width + right.width) / 2.0
            min_separation = avg_width * 0.35

            if abs(right_cx - left_cx) >= min_separation:
                return frames

            source_center_x = (left_cx + right_cx) / 2.0
            source_center_y = (
                (left.top + (left.height / 2.0)) + (right.top + (right.height / 2.0))
            ) / 2.0
            width = avg_width
            height = (left.height + right.height) / 2.0
        else:
            source = left if left is not None else right
            source_center_x = source.left + (source.width / 2.0)
            source_center_y = source.top + (source.height / 2.0)
            width = source.width
            height = source.height

        gap = max(0.02, width * 0.10)
        left_center_x = self._clamp(source_center_x - ((width + gap) / 2.0), width / 2.0, 1.0 - (width / 2.0))
        right_center_x = self._clamp(source_center_x + ((width + gap) / 2.0), width / 2.0, 1.0 - (width / 2.0))
        center_y = self._clamp(source_center_y, height / 2.0, 1.0 - (height / 2.0))

        return {
            "left": HandFrame(
                left=left_center_x - (width / 2.0),
                top=center_y - (height / 2.0),
                width=width,
                height=height,
            ),
            "right": HandFrame(
                left=right_center_x - (width / 2.0),
                top=center_y - (height / 2.0),
                width=width,
                height=height,
            ),
        }

    def _both_hands_present(self, hands_data: HandsData) -> bool:
        return hands_data.camera.has_left and hands_data.camera.has_right

    def _pause(self, reason: str):
        if self._paused and self._status == reason:
            return

        if self.pause_on_hand_loss:
            self.action.release_all_keys()

        self._hovered_slots.clear()
        self._paused = True
        self._resume_counter = 0
        self._status = reason
        self._last_event = ""
        self._last_confidence = 0.0

    def _resume_if_stable(self, hands_data: HandsData):
        if self.require_both_hands and not self._both_hands_present(hands_data):
            self._pause("Typing Paused: both hands required")
            return False

        self._resume_counter += 1
        if self._resume_counter < self.resume_stability_frames:
            self._status = "Typing Paused: waiting for stable hands..."
            return False

        self._paused = False
        self._status = "Keyboard Ready (Display Only)"
        return True

    def _update_overlay_only(self, hands_data: HandsData):
        camera_hands = self._get_hands_by_side(hands_data.camera)
        candidate_frames = {
            "left": self._compute_hand_frame("left", camera_hands.get("left")),
            "right": self._compute_hand_frame("right", camera_hands.get("right")),
        }

        self._update_active_frames(candidate_frames, recenter=self._paused)
        active_frames = self._spread_overlay_frames(self._active_frames)
        if active_frames.get("left") is None and active_frames.get("right") is None:
            active_frames = self._fallback_overlay_frames()

        self._set_overlay_keys(self._build_overlay_keys(active_frames))
        self._update_drag_bounds(active_frames)
        unified_frame = self._resolve_unified_frame(active_frames) if not self.keyboard_split_layout else None

        if self.require_both_hands and not self._both_hands_present(hands_data):
            self._pause("Typing Paused: both hands required")
            return False

        if self._paused:
            self._resume_if_stable(hands_data)
            if self._paused:
                return False

        if self.require_both_hands and (
            candidate_frames["left"] is None or candidate_frames["right"] is None
        ):
            self._pause("Typing Paused: both hands required")
            return False

        hovered_slots = set()
        for side in ("left", "right"):
            frame = unified_frame if unified_frame is not None else active_frames.get(side)
            camera_hand = camera_hands.get(side)
            if frame is None or camera_hand is None or not camera_hand.exists:
                continue

            for finger_name in self._finger_names():
                tip = self._get_tip(camera_hand, finger_name)
                if tip is None:
                    continue
                slot = self._map_tip_to_slot(side, tip, frame)
                if slot is not None:
                    hovered_slots.add(str(slot["id"]))

        self._hovered_slots = hovered_slots
        self._status = "Keyboard Ready (Display Only)"
        self._last_event = ""
        self._last_confidence = 0.0
        return False

    def update(self, hands_data: HandsData, frame_capture_ts_ns=None):
        # frame_capture_ts_ns intentionally unused in display-only mode.
        return self._update_overlay_only(hands_data)

    def detect_gesture(self, hands_data: HandsData):
        return True, hands_data

    def execute_action(self, data):
        return

    def reset(self):
        self.action.release_all_keys()
        self._hovered_slots.clear()
        self._overlay_keys = []
        self._overlay_by_id = {}
        self._active_frames = {"left": None, "right": None}
        self._drag_bounds_by_side = {}
        self._anchor_avg = {"left": None, "right": None}
        self._size_avg = {"left": None, "right": None}
        self._paused = True
        self._resume_counter = 0
        self._status = "Keyboard Initializing..."
        self._single_hand_side_hint = None
        self._last_event = ""
        self._last_confidence = 0.0

    @property
    def is_active(self):
        return not self._paused

    @property
    def current_state(self):
        return self._status

    def get_overlay_data(self):
        drag_bounds = []
        for side, bound in self._drag_bounds_by_side.items():
            if bound is None:
                continue
            drag_bounds.append(
                {
                    "side": side,
                    "x": bound.left,
                    "y": bound.top,
                    "w": bound.width,
                    "h": bound.height,
                }
            )

        return {
            "enabled": True,
            "calibrated": not self._paused,
            "status": self._status,
            "keys": self._overlay_keys,
            "drag_bounds": drag_bounds,
            "hovered_keys": list(self._hovered_slots),
            "pressed_keys": [],
            "last_event": "",
            "press_confidence": 0.0,
            "finger_diagnostics": [],
            "calibration": {"active": False, "progress": 1.0},
        }
