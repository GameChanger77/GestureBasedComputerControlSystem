import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

from backend.HandsData import HandsData
from backend.gestures.GestureRecognizer import GestureRecognizer
from backend.gestures.GestureUtils import get_finger_angle
from backend.keyboard.KeyCodes import LOCK_KEYS, MODIFIER_KEYS, REPEATABLE_KEYS


class FingerPhase(Enum):
    HOVER = "hover"
    PRESSED = "pressed"


@dataclass
class FingerRuntime:
    phase: FingerPhase = FingerPhase.HOVER
    active_slot_id: Optional[str] = None
    active_action_key: Optional[str] = None
    last_press_ts: float = 0.0
    last_repeat_ts: float = 0.0
    press_confidence: float = 0.0
    hover_slot_id: Optional[str] = None
    hover_frames: int = 0
    hover_baseline_bend: Optional[float] = None
    hover_baseline_radius: Optional[float] = None
    hover_baseline_z: Optional[float] = None
    last_bend: Optional[float] = None
    last_radius: Optional[float] = None
    last_z: Optional[float] = None
    last_ts: Optional[float] = None


@dataclass
class HandFrame:
    left: float
    top: float
    width: float
    height: float


class AirTypingGesture(GestureRecognizer):
    """
    Fingertip-anchored in-air typing recognizer.

    Each hand owns half the keyboard and that half follows the hand in real time.
    Presses are detected from finger bend and fingertip radius change relative to the wrist.
    """

    def __init__(self, action, config, priority=15):
        super().__init__(action, priority=priority)
        self.config = config

        self.require_both_hands = bool(self.config.get("keyboard_require_both_hands", True))
        self.pause_on_hand_loss = bool(self.config.get("keyboard_pause_on_hand_loss", True))
        self.resume_stability_frames = int(self.config.get("keyboard_resume_stability_frames", 4))
        self.use_thumb_fingers = bool(self.config.get("keyboard_use_thumb_fingers", True))
        self.active_fingers = self.config.get("keyboard_active_fingers", ["thumb", "index", "middle", "ring", "pinky"])
        if not isinstance(self.active_fingers, list) or not self.active_fingers:
            self.active_fingers = ["thumb", "index", "middle", "ring", "pinky"]

        self.assign_hands_by_x = bool(self.config.get("keyboard_assign_hands_by_x", True))
        self.flip_x_for_mapping = bool(
            self.config.get(
                "keyboard_flip_x_for_mapping",
                self.config.get("preview_flip_horizontal", True),
            )
        )

        # Timing / debounce
        self.press_hover_frames = int(self.config.get("keyboard_press_hover_frames", 2))
        self.min_refractory_ms = int(self.config.get("keyboard_min_key_refractory_ms", 130))
        self.min_global_key_interval_ms = int(self.config.get("keyboard_min_global_key_interval_ms", 35))
        self.repeat_delay_ms = int(self.config.get("keyboard_repeat_delay_ms", 450))
        self.repeat_rate_hz = int(self.config.get("keyboard_repeat_rate_hz", 8))

        # Wrist-relative press model
        self.hover_baseline_alpha = float(self.config.get("keyboard_hover_baseline_alpha", 0.15))
        self.press_bend_threshold = float(self.config.get("keyboard_press_bend_threshold_deg", 38.0))
        self.press_bend_delta_threshold = float(self.config.get("keyboard_press_bend_delta_deg", 12.0))
        self.press_radius_drop_threshold = float(self.config.get("keyboard_press_radius_drop", 0.05))
        self.release_bend_threshold = float(self.config.get("keyboard_release_bend_threshold_deg", 18.0))
        self.release_radius_drop_threshold = float(self.config.get("keyboard_release_radius_drop", 0.018))
        self.press_depth_threshold = float(self.config.get("keyboard_press_depth_threshold", 0.010))
        self.press_depth_velocity_threshold = float(self.config.get("keyboard_press_depth_velocity_threshold", 0.02))
        self.release_depth_threshold = float(self.config.get("keyboard_release_depth_threshold", 0.004))

        # Hand-following split-keyboard geometry
        self.wrist_ema_alpha = float(self.config.get("keyboard_wrist_ema_alpha", 0.28))
        self.half_width_scale = float(self.config.get("keyboard_hand_half_width_scale", 3.2))
        self.half_width_min = float(self.config.get("keyboard_hand_half_width_min", 0.22))
        self.half_width_max = float(self.config.get("keyboard_hand_half_width_max", 0.40))
        self.half_height_ratio = float(self.config.get("keyboard_hand_height_ratio", 0.72))
        self.half_upward_bias = float(self.config.get("keyboard_hand_upward_bias", 0.70))
        self.half_vertical_offset = float(self.config.get("keyboard_hand_vertical_offset", -0.015))
        self.half_horizontal_offset_left = float(self.config.get("keyboard_hand_horizontal_offset_left", 0.0))
        self.half_horizontal_offset_right = float(self.config.get("keyboard_hand_horizontal_offset_right", 0.0))
        self.half_vertical_offset_left = float(self.config.get("keyboard_hand_vertical_offset_left", self.half_vertical_offset))
        self.half_vertical_offset_right = float(self.config.get("keyboard_hand_vertical_offset_right", self.half_vertical_offset))
        self.finger_anchor_row = float(self.config.get("keyboard_finger_anchor_row", 0.20))
        self.finger_anchor_mix_x = float(self.config.get("keyboard_finger_anchor_mix_x", 0.92))
        self.finger_anchor_mix_y = float(self.config.get("keyboard_finger_anchor_mix_y", 0.90))
        self.drag_deadzone_margin_x = float(self.config.get("keyboard_drag_deadzone_margin_x", 0.14))
        self.drag_deadzone_margin_y = float(self.config.get("keyboard_drag_deadzone_margin_y", 0.18))
        self.size_ema_alpha = float(self.config.get("keyboard_hand_size_ema_alpha", 0.22))

        self.debug_enabled = bool(self.config.get("debug_mode", False))
        self._debug_log_interval_sec = float(self.config.get("keyboard_debug_log_interval_sec", 0.8))

        self._paused = True
        self._status = "Calibrating..."
        self._resume_counter = 0

        self._state_by_finger: Dict[str, FingerRuntime] = {}
        self._held_modifiers = set()
        self._last_event = ""
        self._last_confidence = 0.0
        self._last_debug_log_ts = 0.0
        self._last_global_press_ts = 0.0

        self._anchor_avg: Dict[str, Optional[Tuple[float, float]]] = {"left": None, "right": None}
        self._size_avg: Dict[str, Optional[Tuple[float, float]]] = {"left": None, "right": None}
        self._overlay_keys = []
        self._active_frames: Dict[str, Optional[HandFrame]] = {"left": None, "right": None}
        self._drag_bounds_by_side: Dict[str, HandFrame] = {}
        self._hovered_slots = set()

        self._rows_by_side = self._build_split_rows()

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
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    @staticmethod
    def _clamp(value: float, min_value: float, max_value: float) -> float:
        return max(min_value, min(max_value, value))

    def _finger_names(self) -> List[str]:
        fingers = [f for f in self.active_fingers if f in {"thumb", "index", "middle", "ring", "pinky"}]
        if not fingers:
            fingers = ["index", "middle"]
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
        if left is None:
            return {"left": right, "right": right}
        if right is None:
            return {"left": left, "right": left}

        lw = self._normalized_point(left.wrist)
        rw = self._normalized_point(right.wrist)
        if lw is None or rw is None:
            return {"left": left, "right": right}

        if lw[0] <= rw[0]:
            return {"left": left, "right": right}
        return {"left": right, "right": left}

    def _get_state(self, finger_id: str) -> FingerRuntime:
        if finger_id not in self._state_by_finger:
            self._state_by_finger[finger_id] = FingerRuntime()
        return self._state_by_finger[finger_id]

    def _both_hands_present(self, hands_data: HandsData) -> bool:
        return hands_data.camera.has_left and hands_data.camera.has_right

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
            # Fallback when fingertips are temporarily occluded.
            anchor_x_raw = wrist[0]
            anchor_y_raw = wrist[1]

        prev_anchor = self._anchor_avg.get(side)
        if prev_anchor is None:
            anchor_x = anchor_x_raw
            anchor_y = anchor_y_raw
        else:
            a = self.wrist_ema_alpha
            anchor_x = prev_anchor[0] * (1.0 - a) + anchor_x_raw * a
            anchor_y = prev_anchor[1] * (1.0 - a) + anchor_y_raw * a
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
            width = prev_size[0] * (1.0 - sa) + width * sa
            height = prev_size[1] * (1.0 - sa) + height * sa
        self._size_avg[side] = (width, height)

        # Place the keyboard so fingertips sit on upper rows (not near the wrist).
        vertical_offset = self.half_vertical_offset_left if side == "left" else self.half_vertical_offset_right
        horizontal_offset = self.half_horizontal_offset_left if side == "left" else self.half_horizontal_offset_right

        top_raw = anchor_y - (height * self.finger_anchor_row) + vertical_offset
        center_x = self._clamp(anchor_x + horizontal_offset, width / 2.0, 1.0 - width / 2.0)
        center_y = self._clamp(top_raw + (height / 2.0), height / 2.0, 1.0 - height / 2.0)

        left = center_x - width / 2.0
        top = center_y - height / 2.0
        return HandFrame(left=left, top=top, width=width, height=height)

    def _slot_from_uv(self, side: str, u: float, v: float) -> Optional[Dict[str, object]]:
        if u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0:
            return None

        rows = self._rows_by_side[side]
        row_count = len(rows)
        row_idx = min(row_count - 1, max(0, int(v * row_count)))
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

    def _get_tip(self, hand, finger_name: str) -> Optional[Tuple[float, float, float]]:
        if hand is None or not hand.exists:
            return None
        finger = getattr(hand, finger_name, None)
        if finger is None or finger.tip is None:
            return None
        return self._normalized_point(finger.tip)

    def _get_finger_bend_radius(self, wrist_hand, finger_name: str) -> Tuple[Optional[float], Optional[float]]:
        if wrist_hand is None or not wrist_hand.exists:
            return None, None

        finger = getattr(wrist_hand, finger_name, None)
        if finger is None or finger.tip is None:
            return None, None

        angle = get_finger_angle(finger)
        bend = max(0.0, 180.0 - angle)

        tip = self._normalized_point(finger.tip)
        if tip is None:
            return None, None

        radius = math.sqrt(tip[0] * tip[0] + tip[1] * tip[1] + tip[2] * tip[2])
        return bend, radius

    def _tap_key(self, key_id: str):
        self.action.tap_key(key_id)
        self._last_event = f"tap:{key_id}"
        if self.debug_enabled:
            print(f"[AIRTYPE] key_tap key={key_id}")

    def _key_down(self, key_id: str):
        self.action.key_down(key_id)
        self._held_modifiers.add(key_id)
        self._last_event = f"down:{key_id}"
        if self.debug_enabled:
            print(f"[AIRTYPE] key_down key={key_id}")

    def _key_up(self, key_id: str):
        self.action.key_up(key_id)
        self._held_modifiers.discard(key_id)
        self._last_event = f"up:{key_id}"
        if self.debug_enabled:
            print(f"[AIRTYPE] key_up key={key_id}")

    def _process_press(self, finger_id: str, slot: Dict[str, object], confidence: float):
        state = self._get_state(finger_id)
        action_key = str(slot["key"])

        state.phase = FingerPhase.PRESSED
        state.active_slot_id = str(slot["id"])
        state.active_action_key = action_key
        state.last_press_ts = time.time()
        state.last_repeat_ts = state.last_press_ts
        state.press_confidence = confidence
        self._last_confidence = confidence

        if action_key in MODIFIER_KEYS:
            self._key_down(action_key)
        elif action_key in LOCK_KEYS:
            self._tap_key(action_key)
        else:
            self._tap_key(action_key)

    def _process_release(self, finger_id: str):
        state = self._get_state(finger_id)
        active_action = state.active_action_key
        if active_action in MODIFIER_KEYS:
            self._key_up(active_action)

        state.phase = FingerPhase.HOVER
        state.active_slot_id = None
        state.active_action_key = None
        state.press_confidence = 0.0

    def _maybe_repeat(self, state: FingerRuntime) -> bool:
        if state.active_action_key not in REPEATABLE_KEYS:
            return False

        now = time.time()
        repeat_delay = self.repeat_delay_ms / 1000.0
        repeat_interval = 1.0 / max(self.repeat_rate_hz, 1)
        if now - state.last_press_ts < repeat_delay:
            return False
        if now - state.last_repeat_ts < repeat_interval:
            return False

        self._tap_key(state.active_action_key)
        state.last_repeat_ts = now
        return True

    def _pause(self, reason: str):
        if self._paused and self._status == reason:
            return

        if self.pause_on_hand_loss:
            self.action.release_all_keys()

        self._held_modifiers.clear()
        self._hovered_slots.clear()

        for state in self._state_by_finger.values():
            state.phase = FingerPhase.HOVER
            state.active_slot_id = None
            state.active_action_key = None
            state.press_confidence = 0.0
            state.hover_slot_id = None
            state.hover_frames = 0
            state.hover_baseline_bend = None
            state.hover_baseline_radius = None
            state.hover_baseline_z = None
            state.last_bend = None
            state.last_radius = None
            state.last_z = None
            state.last_ts = None

        self._paused = True
        self._resume_counter = 0
        self._status = reason

    def _resume_if_stable(self, hands_data: HandsData):
        if self.require_both_hands and not self._both_hands_present(hands_data):
            self._pause("Typing Paused: both hands required")
            return False

        self._resume_counter += 1
        if self._resume_counter < self.resume_stability_frames:
            self._status = "Typing Paused: waiting for stable hands..."
            return False

        self._paused = False
        self._status = "Keyboard Ready (Wrist Relative)"
        return False

    def _build_overlay_keys(self, frames: Dict[str, Optional[HandFrame]]) -> List[Dict[str, object]]:
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
                row_top = frame.top + row_h * row_idx
                row_total = sum(float(slot["w"]) for slot in row)
                if row_total <= 1e-6:
                    continue

                accum = 0.0
                for slot in row:
                    slot_w = float(slot["w"]) / row_total
                    x = frame.left + frame.width * accum
                    w = frame.width * slot_w
                    key_rects.append(
                        {
                            "id": str(slot["id"]),
                            "label": str(slot["label"]),
                            "x": x,
                            "y": row_top,
                            "w": w,
                            "h": row_h,
                        }
                    )
                    accum += slot_w

        return key_rects

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
            new_center_x = self._clamp(
                active_center_x + shift_x,
                active.width / 2.0,
                1.0 - (active.width / 2.0),
            )
            new_center_y = self._clamp(
                active_center_y + shift_y,
                active.height / 2.0,
                1.0 - (active.height / 2.0),
            )
            self._active_frames[side] = HandFrame(
                left=new_center_x - (active.width / 2.0),
                top=new_center_y - (active.height / 2.0),
                width=active.width,
                height=active.height,
            )

    def _fallback_overlay_frames(self) -> Dict[str, Optional[HandFrame]]:
        """
        Provide a stable split-keyboard frame when hand-derived frames are unavailable.
        """
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
        hands_data: HandsData,
    ) -> Dict[str, Optional[HandFrame]]:
        """
        Ensure overlay shows two visible keyboard halves.

        When only one hand is detected (or both frames overlap heavily due hand-loss fallback),
        synthesize separated left/right frames for UI rendering only.
        """
        left = frames.get("left")
        right = frames.get("right")

        if left is None and right is None:
            return frames

        if left is not None and right is not None:
            left_cx = left.left + (left.width / 2.0)
            right_cx = right.left + (right.width / 2.0)
            avg_width = (left.width + right.width) / 2.0
            min_separation = avg_width * 0.35

            # Keep naturally separated two-hand overlay untouched.
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

    def update(self, hands_data: HandsData, frame_capture_ts_ns=None):
        action_executed = False

        camera_hands = self._get_hands_by_side(hands_data.camera)
        wrist_hands = self._get_hands_by_side(hands_data.wrist)

        candidate_frames = {
            "left": self._compute_hand_frame("left", camera_hands.get("left")),
            "right": self._compute_hand_frame("right", camera_hands.get("right")),
        }

        # While calibrating we recenter keyboards around current hands; after that,
        # keep keyboards fixed unless hands leave the surrounding deadzone bounds.
        self._update_active_frames(candidate_frames, recenter=self._paused)

        active_frames = self._spread_overlay_frames(self._active_frames, hands_data)
        if active_frames.get("left") is None and active_frames.get("right") is None:
            active_frames = self._fallback_overlay_frames()

        self._overlay_keys = self._build_overlay_keys(active_frames)
        self._update_drag_bounds(active_frames)

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
        now = time.time()
        refractory_seconds = self.min_refractory_ms / 1000.0
        global_interval_seconds = self.min_global_key_interval_ms / 1000.0

        for side in ("left", "right"):
            frame = active_frames.get(side)
            camera_hand = camera_hands.get(side)
            wrist_hand = wrist_hands.get(side)
            if frame is None or camera_hand is None or wrist_hand is None:
                continue

            for finger_name in self._finger_names():
                finger_id = f"{side}_{finger_name}"
                state = self._get_state(finger_id)

                tip = self._get_tip(camera_hand, finger_name)
                bend, radius = self._get_finger_bend_radius(wrist_hand, finger_name)

                if tip is None or bend is None or radius is None:
                    if state.phase == FingerPhase.PRESSED:
                        self._process_release(finger_id)
                    state.hover_slot_id = None
                    state.hover_frames = 0
                    state.hover_baseline_bend = None
                    state.hover_baseline_radius = None
                    state.hover_baseline_z = None
                    state.last_z = None
                    state.last_ts = None
                    continue

                slot = self._map_tip_to_slot(side, tip, frame)
                if slot is not None:
                    hovered_slots.add(str(slot["id"]))

                if slot is not None and state.hover_slot_id == str(slot["id"]):
                    state.hover_frames += 1
                elif slot is not None:
                    state.hover_slot_id = str(slot["id"])
                    state.hover_frames = 1
                    state.hover_baseline_bend = bend
                    state.hover_baseline_radius = radius
                    state.hover_baseline_z = tip[2]
                else:
                    state.hover_slot_id = None
                    state.hover_frames = 0
                    state.hover_baseline_bend = None
                    state.hover_baseline_radius = None
                    state.hover_baseline_z = None

                if (
                    slot is not None
                    and state.phase == FingerPhase.HOVER
                    and state.hover_frames < self.press_hover_frames
                ):
                    if state.hover_baseline_bend is None:
                        state.hover_baseline_bend = bend
                    else:
                        a = self.hover_baseline_alpha
                        state.hover_baseline_bend = (1.0 - a) * state.hover_baseline_bend + a * bend

                    if state.hover_baseline_radius is None:
                        state.hover_baseline_radius = radius
                    else:
                        a = self.hover_baseline_alpha
                        state.hover_baseline_radius = (1.0 - a) * state.hover_baseline_radius + a * radius
                    if state.hover_baseline_z is None:
                        state.hover_baseline_z = tip[2]
                    else:
                        a = self.hover_baseline_alpha
                        state.hover_baseline_z = (1.0 - a) * state.hover_baseline_z + a * tip[2]

                baseline_bend = state.hover_baseline_bend if state.hover_baseline_bend is not None else bend
                baseline_radius = state.hover_baseline_radius if state.hover_baseline_radius is not None else radius
                baseline_z = state.hover_baseline_z if state.hover_baseline_z is not None else tip[2]

                bend_delta = max(0.0, bend - baseline_bend)
                radius_drop = max(0.0, baseline_radius - radius)
                depth_delta = max(0.0, baseline_z - tip[2])

                z_velocity_toward_camera = 0.0
                if state.last_z is not None and state.last_ts is not None:
                    dt = max(now - state.last_ts, 1e-3)
                    z_velocity_toward_camera = (state.last_z - tip[2]) / dt

                press_signal = (
                    (
                        (bend >= self.press_bend_threshold or bend_delta >= self.press_bend_delta_threshold)
                        and radius_drop >= self.press_radius_drop_threshold
                    )
                    or (bend_delta >= (self.press_bend_delta_threshold * 1.7))
                    or (
                        depth_delta >= self.press_depth_threshold
                        and z_velocity_toward_camera >= self.press_depth_velocity_threshold
                    )
                )

                if state.phase == FingerPhase.HOVER:
                    if (
                        slot is not None
                        and state.hover_frames >= self.press_hover_frames
                        and press_signal
                        and (now - state.last_press_ts) >= refractory_seconds
                        and (now - self._last_global_press_ts) >= global_interval_seconds
                    ):
                        bend_conf = max(bend / max(self.press_bend_threshold, 1e-6), bend_delta / max(self.press_bend_delta_threshold, 1e-6))
                        radius_conf = radius_drop / max(self.press_radius_drop_threshold, 1e-6)
                        confidence = max(0.0, min(1.0, 0.5 * (bend_conf + radius_conf)))
                        self._process_press(finger_id, slot, confidence)
                        self._last_global_press_ts = now
                        action_executed = True

                elif state.phase == FingerPhase.PRESSED:
                    action_executed = self._maybe_repeat(state) or action_executed

                    release_by_slot = slot is None or str(slot["id"]) != state.active_slot_id
                    release_by_depth = depth_delta <= self.release_depth_threshold
                    if state.active_action_key in MODIFIER_KEYS:
                        release_signal = (
                            bend <= self.release_bend_threshold
                            and radius_drop <= self.release_radius_drop_threshold
                            and release_by_depth
                        )
                    else:
                        release_signal = (
                            bend <= self.release_bend_threshold
                            or radius_drop <= self.release_radius_drop_threshold
                            or release_by_depth
                        )

                    if release_by_slot or release_signal:
                        self._process_release(finger_id)

                state.last_bend = bend
                state.last_radius = radius
                state.last_z = tip[2]
                state.last_ts = now

        self._hovered_slots = hovered_slots

        if self.debug_enabled and (now - self._last_debug_log_ts) >= self._debug_log_interval_sec:
            li = self._get_state("left_index")
            ri = self._get_state("right_index")
            print(
                "[AIRTYPE] "
                f"status='{self._status}' "
                f"L(phase={li.phase.value},slot={li.hover_slot_id},bend={li.last_bend},hover={li.hover_frames}) "
                f"R(phase={ri.phase.value},slot={ri.hover_slot_id},bend={ri.last_bend},hover={ri.hover_frames}) "
                f"last={self._last_event}"
            )
            self._last_debug_log_ts = now

        self._status = "Keyboard Ready (Wrist Relative)"
        return action_executed

    def detect_gesture(self, hands_data: HandsData):
        # Not used directly; update() handles full flow.
        return True, hands_data

    def execute_action(self, data):
        # Not used directly; update() handles full flow.
        return

    def reset(self):
        self.action.release_all_keys()
        self._held_modifiers.clear()
        self._state_by_finger.clear()
        self._hovered_slots.clear()
        self._overlay_keys = []
        self._active_frames = {"left": None, "right": None}
        self._drag_bounds_by_side = {}
        self._anchor_avg = {"left": None, "right": None}
        self._size_avg = {"left": None, "right": None}
        self._paused = True
        self._resume_counter = 0
        self._status = "Calibrating..."
        self._last_event = ""
        self._last_confidence = 0.0
        self._last_global_press_ts = 0.0

    @property
    def is_active(self):
        return not self._paused

    @property
    def current_state(self):
        return self._status

    def get_overlay_data(self):
        pressed_slots = {
            s.active_slot_id
            for s in self._state_by_finger.values()
            if s.phase == FingerPhase.PRESSED and s.active_slot_id
        }
        drag_bounds = []
        for side in ("left", "right"):
            bound = self._drag_bounds_by_side.get(side)
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
            "pressed_keys": list(pressed_slots),
            "last_event": self._last_event,
            "press_confidence": self._last_confidence,
        }
