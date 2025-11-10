import numpy as np
from typing import Dict, List, Tuple
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
        # Structure: {(hand_label, finger_idx, landmark_idx): deque of positions}
        self.history: Dict[Tuple, deque] = {}

        self.frame_count = 0

    def smooth_hands_data(
            self,
            hands_data: Dict[str, List[List[Tuple[float, float, float]]]]
    ) -> Dict[str, List[List[Tuple[float, float, float]]]]:
        """
        Smooth hand landmarks data using moving average.

        Args:
            hands_data (dict): Hand data in the format:
                              {'Left': [finger1, finger2, ...], 'Right': [...]}
                              Each finger is a list of (x, y, z) landmark tuples.

        Returns:
            dict: Smoothed hand data in the same format.
        """
        smoothed_hands_data = {}

        for hand_label, fingers in hands_data.items():
            smoothed_fingers = []

            for finger_idx, finger in enumerate(fingers):
                smoothed_finger = []

                for landmark_idx, (x, y, z) in enumerate(finger):
                    # Create a unique key for this landmark
                    landmark_key = (hand_label, finger_idx, landmark_idx)

                    # Get or create history for this landmark
                    if landmark_key not in self.history:
                        self.history[landmark_key] = deque(maxlen=self.window_size)

                    # Add current position to history
                    self.history[landmark_key].append(np.array([x, y, z]))

                    # Calculate average of all positions in history
                    if len(self.history[landmark_key]) > 0:
                        positions = np.array(list(self.history[landmark_key]))
                        smoothed_pos = np.mean(positions, axis=0)
                        smoothed_pos = tuple(smoothed_pos)
                    else:
                        smoothed_pos = (x, y, z)

                    smoothed_finger.append(smoothed_pos)

                smoothed_fingers.append(smoothed_finger)

            smoothed_hands_data[hand_label] = smoothed_fingers

        # Debug output
        if self.debug:
            self.frame_count += 1
            if self.frame_count % 30 == 0:
                print(f"Frame {self.frame_count}: Moving average smoother (window_size={self.window_size})")

        return smoothed_hands_data

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