from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

@dataclass
class HandFrame:
    left: float
    top: float
    width: float
    height: float


@dataclass
class SurfaceLayoutState:
    active_frames: Dict[str, Optional[HandFrame]]
    unified_frame: Optional[HandFrame]
    overlay_keys: List[Dict[str, object]]
    drag_bounds_by_side: Dict[str, HandFrame]
    extra_overlay: Dict[str, object]


class KeyboardSurfaceBase:
    def __init__(self, config, *, flip_x_for_mapping: bool, screen_width: int, screen_height: int):
        self.config = config
        self.flip_x_for_mapping = bool(flip_x_for_mapping)
        self.screen_width = max(1, int(screen_width))
        self.screen_height = max(1, int(screen_height))

    @staticmethod
    def _clamp(value: float, min_value: float, max_value: float) -> float:
        return max(min_value, min(max_value, value))

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
        return ((dx * dx) + (dy * dy) + (dz * dz)) ** 0.5

    def _get_tip(self, hand, finger_name: str) -> Optional[Tuple[float, float, float]]:
        if hand is None or not hand.exists:
            return None
        finger = getattr(hand, finger_name, None)
        if finger is None or finger.tip is None:
            return None
        return self._normalized_point(finger.tip)

    def _get_camera_hands(self, coord_space) -> Dict[str, object]:
        return {
            "left": coord_space.left if coord_space.has_left else None,
            "right": coord_space.right if coord_space.has_right else None,
        }

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

    def _build_overlay_keys(
        self,
        rows: List[List[Dict[str, object]]],
        frame: Optional[HandFrame],
    ) -> List[Dict[str, object]]:
        if frame is None or not rows:
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

    def update_layout(self, hands_data, *, paused: bool, rows: List[List[Dict[str, object]]]) -> SurfaceLayoutState:
        raise NotImplementedError

    def shutdown(self):
        return

