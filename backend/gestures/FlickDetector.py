from typing import Optional, Sequence, Tuple

from backend.gestures.MotionTracker import MotionTracker

FlickDirection = str


class FlickDetector:
    """
    Generic directional flick detector backed by MotionTracker.

    Feed normalized 2D samples and call detect() to retrieve at most one
    directional event until reset() is called.
    """

    def __init__(
        self,
        *,
        min_samples: int = 3,
        min_displacement: float = 0.10,
        min_speed: float = 0.35,
        dominance_ratio: float = 1.3,
        allowed_directions: Sequence[FlickDirection] = ("left", "right", "up", "down"),
        buffer_frames: int = 24,
        velocity_window_frames: int = 5,
    ):
        self.min_samples = max(2, int(min_samples))
        self.min_displacement = max(0.0, float(min_displacement))
        self.min_speed = max(0.0, float(min_speed))
        self.dominance_ratio = max(1.0, float(dominance_ratio))
        self.allowed_directions = set(str(d) for d in allowed_directions)
        self._velocity_window_frames = max(2, int(velocity_window_frames))
        self._motion = MotionTracker(buffer_frames=max(self.min_samples + 2, int(buffer_frames)), fps=30)
        self._fired = False

    def reset(self):
        self._motion.clear()
        self._fired = False

    def add_sample(self, point_xy: Tuple[float, float], timestamp_s: float):
        if self._fired:
            return
        if point_xy is None:
            return
        x, y = point_xy
        self._motion.add_frame((float(x), float(y), 0.0), timestamp_s=timestamp_s)

    def detect(self) -> Optional[FlickDirection]:
        """
        Return a single direction once per reset, or None if no valid flick yet.
        """
        if self._fired:
            return None
        if self._motion.frame_count < self.min_samples:
            return None

        displacement_vec, displacement_mag = self._motion.get_displacement()
        if displacement_mag < self.min_displacement:
            return None

        velocity_vec, speed = self._motion.get_velocity(window_frames=self._velocity_window_frames)
        if speed < self.min_speed:
            return None

        dx = float(displacement_vec[0])
        dy = float(displacement_vec[1])
        abs_dx = abs(dx)
        abs_dy = abs(dy)

        direction: Optional[FlickDirection] = None
        if abs_dx >= (abs_dy * self.dominance_ratio):
            direction = "right" if dx > 0 else "left"
        elif abs_dy >= (abs_dx * self.dominance_ratio):
            direction = "down" if dy > 0 else "up"

        if direction is None:
            return None
        if direction not in self.allowed_directions:
            return None

        self._fired = True
        return direction
