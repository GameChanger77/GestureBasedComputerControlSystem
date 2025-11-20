import numpy as np
from typing import Tuple
from collections import deque


class LandmarkSmoother:
    """
    Smooths hand landmarks using a simple moving average filter.
    Keeps the last N frames and averages landmark positions.
    """

    def __init__(self, window_size: int = 5, debug: bool = False):
        """
        Initialize the landmark smoother.

        Args:
            window_size (int): Number of frames to average over.
                             - 3-5: Light smoothing, responsive
                             - 5-10: Medium smoothing
                             - 10+: Heavy smoothing, more lag
                             - Recommended: 5
            debug (bool): Enable debug output
        """
        self.window_size = window_size
        self.debug = debug

        # Storage for historical positions
        # Structure: {(coord_space, hand_label, finger_name, landmark_idx): deque of positions}
        # coord_space: 'wrist' or 'camera'
        # hand_label: 'left' or 'right'
        # finger_name: 'wrist', 'thumb', 'index', 'middle', 'ring', 'pinky'
        self.history = {}

        self.frame_count = 0

    def _smooth_landmark(self, landmark_key: Tuple, position: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """
        Smooth a single landmark position.

        Args:
            landmark_key: Unique identifier for this landmark
            position: Current (x, y, z) position

        Returns:
            Smoothed (x, y, z) position
        """
        # Get or create history for this landmark
        if landmark_key not in self.history:
            self.history[landmark_key] = deque(maxlen=self.window_size)

        # Convert position to numpy array once
        pos_array = np.array(position, dtype=np.float32)
        self.history[landmark_key].append(pos_array)

        # Calculate average directly from deque (avoid list conversion)
        if len(self.history[landmark_key]) == 1:
            # Fast path: only one position in history
            smoothed_pos = pos_array
        else:
            # Stack arrays from deque and compute mean - avoids list() conversion
            smoothed_pos = np.mean(np.stack(self.history[landmark_key]), axis=0)

        return tuple(smoothed_pos)

    def _smooth_hand(self, coord_space: str, hand_label: str, hand) -> None:
        """
        Smooth all landmarks for a single hand in-place.

        Args:
            coord_space: 'wrist' or 'camera'
            hand_label: 'left' or 'right'
            hand: Hand object to smooth (modified in-place)
        """
        if not hand.exists:
            return

        # Import here to avoid circular dependency
        from backend.HandsData import HandsData

        # Smooth wrist
        wrist_key = (coord_space, hand_label, 'wrist', 0)
        hand._wrist = self._smooth_landmark(wrist_key, hand._wrist)

        # Smooth each finger
        for finger_name in ['thumb', 'index', 'middle', 'ring', 'pinky']:
            finger = getattr(hand, finger_name)
            if not finger or len(finger) == 0:
                continue

            # Smooth joints in-place using list comprehension (faster than append loop)
            finger.joints = [
                self._smooth_landmark((coord_space, hand_label, finger_name, idx), pos)
                for idx, pos in enumerate(finger.joints)
            ]

    def smooth_hands_data(self, hands_data):
        """
        Smooth hand landmarks data using moving average.

        Args:
            hands_data: HandsData object with wrist and camera coordinate spaces

        Returns:
            HandsData: The same HandsData object with smoothed coordinates (modified in-place)
        """
        # Smooth wrist-relative coordinates
        self._smooth_hand('wrist', 'left', hands_data.wrist.left)
        self._smooth_hand('wrist', 'right', hands_data.wrist.right)

        # Smooth camera-relative coordinates
        self._smooth_hand('camera', 'left', hands_data.camera.left)
        self._smooth_hand('camera', 'right', hands_data.camera.right)

        # Debug output
        if self.debug:
            self.frame_count += 1
            if self.frame_count % 30 == 0:
                print(f"Frame {self.frame_count}: Moving average smoother (window_size={self.window_size})")

        return hands_data

    def reset(self) -> None:
        """
        Reset the smoother state. Call this when restarting detection or
        switching hands/cameras.
        """
        self.history = {}
        self.frame_count = 0

    def set_window_size(self, size: int) -> None:
        """
        Dynamically adjust the window size.

        Args:
            size (int): New window size (should be > 0)
        """
        if size <= 0:
            raise ValueError("Window size must be positive")
        self.window_size = size
        # Reset history when window size changes to avoid mixing different window sizes
        self.history = {}