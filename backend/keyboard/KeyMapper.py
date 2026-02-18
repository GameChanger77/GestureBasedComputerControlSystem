from typing import Dict, Optional, Tuple

from backend.keyboard.KeyboardCalibration import KeyboardCalibration
from backend.keyboard.KeyboardLayoutUS import KeyboardLayoutUS, KeyRect


class KeyMapper:
    """
    Maps camera-space fingertip points to keyboard keys with simple hysteresis.
    """

    def __init__(
        self,
        layout: KeyboardLayoutUS,
        calibration: KeyboardCalibration,
        sticky_margin: float = 0.18,
        nearest_key_max_distance: float = 0.22,
    ):
        self.layout = layout
        self.calibration = calibration
        self.sticky_margin = sticky_margin
        self.nearest_key_max_distance = nearest_key_max_distance
        self._last_key_by_finger: Dict[str, str] = {}

    def reset(self):
        self._last_key_by_finger.clear()

    def _is_inside_expanded(self, key: KeyRect, lx: float, ly: float, margin: float) -> bool:
        return (
            key.x - margin <= lx <= key.x + key.width + margin
            and key.y - margin <= ly <= key.y + key.height + margin
        )

    def map_finger(self, finger_id: str, tip_point: Tuple[float, float, float]) -> Optional[str]:
        layout_point = self.calibration.camera_to_layout(tip_point)
        if layout_point is None:
            self._last_key_by_finger.pop(finger_id, None)
            return None

        lx, ly = layout_point
        direct = self.layout.key_at(lx, ly)
        if direct is None:
            direct = self.layout.nearest_key(lx, ly, max_distance=self.nearest_key_max_distance)

        previous_id = self._last_key_by_finger.get(finger_id)
        if previous_id:
            previous_key = self.layout.get_key(previous_id)
            if previous_key and self._is_inside_expanded(previous_key, lx, ly, self.sticky_margin):
                return previous_id

        if direct:
            self._last_key_by_finger[finger_id] = direct.key_id
            return direct.key_id

        self._last_key_by_finger.pop(finger_id, None)
        return None

    def get_hovered_keys(self):
        return set(self._last_key_by_finger.values())
