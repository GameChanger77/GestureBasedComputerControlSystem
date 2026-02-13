import numpy as np
from collections import deque


class LandmarkSmoother:
    """
    Smooths hand landmarks using a simple moving average filter.
    Operates on entire hand arrays (21x3) for efficiency.
    """

    def __init__(self, debug: bool = False):
        """
        Initialize the landmark smoother.

        Args:
            debug (bool): Enable debug output
        """
        self.window_size = 2  # number of frames in moving average (more = smoother, less = more responsive)
        self.debug = debug

        # Storage for historical hand positions
        # Structure: {hand_label: deque of (21, 3) numpy arrays}
        self.history = {}
        self.frame_count = 0

    def smooth_hand(self, hand_label: str, landmarks_array: np.ndarray) -> np.ndarray:
        """
        Smooth all landmarks for a hand at once (vectorized operation).

        Args:
            hand_label: Hand identifier ('Left' or 'Right')
            landmarks_array: numpy array of shape (21, 3) with hand landmarks

        Returns:
            Smoothed numpy array of shape (21, 3)
        """
        # Get or create history for this hand
        if hand_label not in self.history:
            self.history[hand_label] = deque(maxlen=self.window_size)
            if self.debug:
                print(f"Created new history for {hand_label}")

        # Ensure array is float32 for consistency
        landmarks_array = landmarks_array.astype(np.float32)
        self.history[hand_label].append(landmarks_array)

        history_len = len(self.history[hand_label])
        if self.debug and self.frame_count % 30 == 0:
            print(f"Hand {hand_label}: history_len={history_len}, window_size={self.window_size}")

        self.frame_count += 1

        # Fast path: only one frame in history
        if history_len == 1:
            return landmarks_array

        # Vectorized average across all frames in history
        # Stack creates (N, 21, 3) array, mean over axis 0 gives (21, 3)
        return np.mean(np.stack(self.history[hand_label]), axis=0, dtype=np.float32)

    def reset(self) -> None:
        """
        Reset the smoother state. Call this when restarting detection or
        switching hands/cameras.
        """
        self.history = {}
        self.frame_count = 0
