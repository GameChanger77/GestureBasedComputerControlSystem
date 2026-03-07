from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from backend.gestures.keyboard_mode.KeyboardSurfaceBase import (
    HandFrame,
    KeyboardSurfaceBase,
    SurfaceLayoutState,
)

class DevOverlayKeyboardSurface(KeyboardSurfaceBase):
    def __init__(self, config, *, flip_x_for_mapping: bool, screen_width: int, screen_height: int):
        super().__init__(
            config,
            flip_x_for_mapping=flip_x_for_mapping,
            screen_width=screen_width,
            screen_height=screen_height,
        )
        self.keyboard_fixed_center_mode = True

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

        self._anchor_avg: Dict[str, Optional[Tuple[float, float]]] = {"left": None, "right": None}
        self._size_avg: Dict[str, Optional[Tuple[float, float]]] = {"left": None, "right": None}
        self._active_frames: Dict[str, Optional[HandFrame]] = {"left": None, "right": None}

    @staticmethod
    def _copy_frame(frame: Optional[HandFrame]) -> Optional[HandFrame]:
        if frame is None:
            return None
        return HandFrame(left=frame.left, top=frame.top, width=frame.width, height=frame.height)

    @staticmethod
    def _frame_center(frame: HandFrame) -> Tuple[float, float]:
        return (frame.left + (frame.width / 2.0), frame.top + (frame.height / 2.0))

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

    def _update_active_frames(self, candidate_frames: Dict[str, Optional[HandFrame]], recenter: bool):
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

    def _update_drag_bounds(self, frames: Dict[str, Optional[HandFrame]]) -> Dict[str, HandFrame]:
        drag_bounds: Dict[str, HandFrame] = {}
        unified_frame = self._resolve_unified_frame(frames)
        if unified_frame is not None:
            drag_bounds["full"] = self._compute_deadzone_frame(unified_frame)
        return drag_bounds

    def update_layout(self, hands_data, *, paused: bool, rows: List[List[Dict[str, object]]]) -> SurfaceLayoutState:
        camera_hands = self._get_camera_hands(hands_data.camera)

        if self.keyboard_fixed_center_mode:
            active_frames = self._fallback_overlay_frames()
            self._active_frames = {
                "left": self._copy_frame(active_frames.get("left")),
                "right": self._copy_frame(active_frames.get("right")),
            }
        else:
            candidate_frames = {
                "left": self._compute_hand_frame("left", camera_hands.get("left")),
                "right": self._compute_hand_frame("right", camera_hands.get("right")),
            }
            self._update_active_frames(candidate_frames, recenter=paused)
            active_frames = self._active_frames
            if active_frames.get("left") is None and active_frames.get("right") is None:
                active_frames = self._fallback_overlay_frames()

        unified_frame = self._resolve_unified_frame(active_frames)
        overlay_keys = self._build_overlay_keys(rows, unified_frame)
        drag_bounds = self._update_drag_bounds(active_frames)

        return SurfaceLayoutState(
            active_frames={
                "left": self._copy_frame(active_frames.get("left")),
                "right": self._copy_frame(active_frames.get("right")),
            },
            unified_frame=self._copy_frame(unified_frame),
            overlay_keys=overlay_keys,
            drag_bounds_by_side=drag_bounds,
            extra_overlay={"surface": "dev"},
        )


