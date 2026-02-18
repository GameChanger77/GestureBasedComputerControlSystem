from dataclasses import dataclass
from typing import Optional, Tuple

from backend.HandsData import HandsData
from backend.keyboard.KeyboardLayoutUS import KeyboardLayoutUS


@dataclass
class CalibrationState:
    is_calibrated: bool = False
    center_x: float = 0.5
    center_y: float = 0.6
    width: float = 0.7
    height: float = 0.2
    top_left_x: float = 0.15
    top_left_y: float = 0.5
    press_plane_z: float = -0.1
    status: str = "Calibrating..."


class KeyboardCalibration:
    """
    Maintains keyboard plane calibration from both hands.

    v1 assumes a mostly frontal camera with minimal roll/pitch compensation.
    """

    def __init__(
        self,
        layout: KeyboardLayoutUS,
        width_scale: float = 2.8,
        min_width: float = 0.45,
        max_width: float = 0.95,
        fixed_mode: bool = True,
        fixed_lock_press_plane: bool = True,
        fixed_center_x: float = 0.5,
        fixed_center_y: float = 0.5,
        fixed_width: float = 0.78,
        fixed_height: float = 0.26,
        y_offset_from_fingertips: float = -0.01,
        y_offset_from_wrists: float = -0.06,
        press_depth_offset: float = 0.02,
    ):
        self.layout = layout
        self.width_scale = width_scale
        self.min_width = min_width
        self.max_width = max_width
        self.fixed_mode = fixed_mode
        self.fixed_lock_press_plane = fixed_lock_press_plane
        self.fixed_center_x = fixed_center_x
        self.fixed_center_y = fixed_center_y
        self.fixed_width = fixed_width
        self.fixed_height = fixed_height
        self.y_offset_from_fingertips = y_offset_from_fingertips
        self.y_offset_from_wrists = y_offset_from_wrists
        self.press_depth_offset = press_depth_offset
        self.state = CalibrationState()

    @staticmethod
    def _clamp(value: float, min_value: float, max_value: float) -> float:
        return max(min_value, min(max_value, value))

    def reset(self):
        self.state = CalibrationState()

    def _get_press_plane_z(self, hands_data: HandsData, fallback: float = -0.1) -> float:
        fingertip_z_values = []
        for hand in (hands_data.camera.left, hands_data.camera.right):
            for tip in [hand.index.tip, hand.middle.tip, hand.ring.tip, hand.pinky.tip]:
                if tip is not None:
                    fingertip_z_values.append(tip[2])

        if fingertip_z_values:
            avg_tip_z = sum(fingertip_z_values) / len(fingertip_z_values)
            return avg_tip_z - self.press_depth_offset
        return fallback

    def _compute_fixed(self, hands_data: HandsData) -> CalibrationState:
        width = self._clamp(self.fixed_width, 0.25, 0.95)
        height = self._clamp(self.fixed_height, 0.12, 0.65)
        center_x = self._clamp(self.fixed_center_x, width / 2.0, 1.0 - width / 2.0)
        center_y = self._clamp(self.fixed_center_y, height / 2.0, 1.0 - height / 2.0)
        top_left_x = center_x - width / 2.0
        top_left_y = center_y - height / 2.0
        press_plane_z = self._get_press_plane_z(hands_data, fallback=self.state.press_plane_z)

        return CalibrationState(
            is_calibrated=True,
            center_x=center_x,
            center_y=center_y,
            width=width,
            height=height,
            top_left_x=top_left_x,
            top_left_y=top_left_y,
            press_plane_z=press_plane_z,
            status="Ready (Fixed Center)",
        )

    def _compute_from_hands(self, hands_data: HandsData) -> Optional[CalibrationState]:
        if self.fixed_mode:
            return self._compute_fixed(hands_data)

        if not hands_data.camera.has_left or not hands_data.camera.has_right:
            return None

        left = hands_data.camera.left
        right = hands_data.camera.right
        if left.wrist is None or right.wrist is None:
            return None

        lx, ly, lz = left.wrist
        rx, ry, rz = right.wrist

        dx = rx - lx
        dy = ry - ly
        wrist_dist = max((dx * dx + dy * dy) ** 0.5, 1e-6)

        width = max(self.min_width, min(self.max_width, wrist_dist * self.width_scale))
        aspect_ratio = self.layout.height / max(self.layout.width, 1e-6)
        height = width * aspect_ratio

        center_x = (lx + rx) / 2.0

        fingertip_y_values = []
        for hand in (hands_data.camera.left, hands_data.camera.right):
            # Anchor Y primarily from index/middle fingertips to align with typing row.
            anchor_tips = [hand.index.tip, hand.middle.tip]
            for tip in anchor_tips:
                if tip is not None:
                    fingertip_y_values.append(tip[1])

        if fingertip_y_values:
            avg_tip_y = sum(fingertip_y_values) / len(fingertip_y_values)
            center_y = avg_tip_y + self.y_offset_from_fingertips
        else:
            center_y = (ly + ry) / 2.0 + self.y_offset_from_wrists

        top_left_x = center_x - width / 2.0
        top_left_y = center_y - height / 2.0

        press_plane_z = self._get_press_plane_z(hands_data, fallback=(lz + rz) / 2.0 - self.press_depth_offset)

        return CalibrationState(
            is_calibrated=True,
            center_x=center_x,
            center_y=center_y,
            width=width,
            height=height,
            top_left_x=top_left_x,
            top_left_y=top_left_y,
            press_plane_z=press_plane_z,
            status="Ready",
        )

    def calibrate(self, hands_data: HandsData) -> bool:
        computed = self._compute_from_hands(hands_data)
        if computed is None:
            self.state.status = "Calibrating..."
            return False

        self.state = computed
        return True

    def smooth_update(self, hands_data: HandsData, alpha: float = 0.12) -> bool:
        computed = self._compute_from_hands(hands_data)
        if computed is None:
            return False

        if not self.state.is_calibrated:
            self.state = computed
            return True

        s = self.state
        if self.fixed_mode:
            # In fixed-center mode, keep geometry fixed and optionally lock press plane
            # to avoid drift-triggered phantom presses.
            s.center_x = computed.center_x
            s.center_y = computed.center_y
            s.width = computed.width
            s.height = computed.height
            s.top_left_x = computed.top_left_x
            s.top_left_y = computed.top_left_y
            if not self.fixed_lock_press_plane:
                s.press_plane_z = s.press_plane_z * (1.0 - alpha) + computed.press_plane_z * alpha
            s.is_calibrated = True
            s.status = computed.status
            return True

        s.center_x = s.center_x * (1.0 - alpha) + computed.center_x * alpha
        s.center_y = s.center_y * (1.0 - alpha) + computed.center_y * alpha
        s.width = s.width * (1.0 - alpha) + computed.width * alpha
        s.height = s.height * (1.0 - alpha) + computed.height * alpha
        s.top_left_x = s.center_x - s.width / 2.0
        s.top_left_y = s.center_y - s.height / 2.0
        s.press_plane_z = s.press_plane_z * (1.0 - alpha) + computed.press_plane_z * alpha
        s.is_calibrated = True
        s.status = "Ready"
        return True

    def camera_to_layout(self, camera_point: Tuple[float, float, float]) -> Optional[Tuple[float, float]]:
        if not self.state.is_calibrated:
            return None

        x, y, _ = camera_point
        if self.state.width <= 1e-6 or self.state.height <= 1e-6:
            return None

        u = (x - self.state.top_left_x) / self.state.width
        v = (y - self.state.top_left_y) / self.state.height
        if u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0:
            return None

        return (u * self.layout.width, v * self.layout.height)
