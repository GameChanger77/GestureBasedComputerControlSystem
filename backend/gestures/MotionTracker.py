from collections import deque
import numpy as np


class MotionTracker:
    """
    Tracks hand motion over time by buffering recent hand positions.

    Provides motion analysis capabilities:
    - Velocity and direction
    - Trajectory path
    - Motion patterns (swipe, clench, circle, etc.)

    Used by MotionGestureRecognizer to validate complete motion sequences.
    """

    def __init__(self, buffer_frames=30, fps=30):
        """
        Initialize the motion tracker.

        Args:
            buffer_frames: Number of frames to keep in history
            fps: Frames per second (for velocity calculations)
        """
        self.buffer_frames = buffer_frames
        self.fps = fps
        self.frame_time = 1.0 / fps

        # Circular buffers for position history
        self.position_buffer = deque(maxlen=buffer_frames)
        self.timestamp_buffer = deque(maxlen=buffer_frames)

        # Current frame counter
        self._frame_count = 0

    def add_frame(self, position, timestamp_s=None):
        """
        Add a new position to the motion buffer.

        Args:
            position: Tuple (x, y, z) representing hand position (or specific landmark)
            timestamp_s: Optional timestamp in seconds. If not provided,
                frame-time-derived timestamps are used.
        """
        if position is not None:
            self.position_buffer.append(np.array(position))
            if timestamp_s is None:
                timestamp = self._frame_count * self.frame_time
            else:
                timestamp = float(timestamp_s)
            self.timestamp_buffer.append(timestamp)
            self._frame_count += 1

    def clear(self):
        """Clear the motion buffer"""
        self.position_buffer.clear()
        self.timestamp_buffer.clear()
        self._frame_count = 0

    def get_velocity(self, window_frames=5):
        """
        Calculate current velocity over a window of recent frames.

        Args:
            window_frames: Number of recent frames to use for calculation

        Returns:
            tuple: (velocity_vector, speed)
                - velocity_vector: np.array [vx, vy, vz] in units/second
                - speed: Scalar speed magnitude
        """
        if len(self.position_buffer) < 2:
            return np.array([0.0, 0.0, 0.0]), 0.0

        # Use recent window for velocity calculation
        window = min(window_frames, len(self.position_buffer))
        recent_positions = list(self.position_buffer)[-window:]
        recent_timestamps = list(self.timestamp_buffer)[-window:]

        # Calculate displacement from first to last in window
        displacement = recent_positions[-1] - recent_positions[0]
        time_delta = recent_timestamps[-1] - recent_timestamps[0]
        if time_delta <= 0:
            # Backward-compatible fallback for invalid/duplicate timestamps.
            time_delta = (window - 1) * self.frame_time

        if time_delta > 0:
            velocity = displacement / time_delta
            speed = np.linalg.norm(velocity)
            return velocity, speed

        return np.array([0.0, 0.0, 0.0]), 0.0

    def get_direction(self):
        """
        Get the overall direction of motion from start to current position.

        Returns:
            np.array: Normalized direction vector [dx, dy, dz]
        """
        if len(self.position_buffer) < 2:
            return np.array([0.0, 0.0, 0.0])

        start_pos = self.position_buffer[0]
        end_pos = self.position_buffer[-1]
        direction = end_pos - start_pos

        magnitude = np.linalg.norm(direction)
        if magnitude > 1e-6:
            return direction / magnitude

        return np.array([0.0, 0.0, 0.0])

    def get_total_distance(self):
        """
        Get total distance traveled along the path.

        Returns:
            float: Total distance
        """
        if len(self.position_buffer) < 2:
            return 0.0

        total_dist = 0.0
        for i in range(1, len(self.position_buffer)):
            total_dist += np.linalg.norm(
                self.position_buffer[i] - self.position_buffer[i-1]
            )

        return total_dist

    def get_displacement(self):
        """
        Get straight-line displacement from start to end.

        Returns:
            tuple: (displacement_vector, displacement_magnitude)
        """
        if len(self.position_buffer) < 2:
            return np.array([0.0, 0.0, 0.0]), 0.0

        displacement = self.position_buffer[-1] - self.position_buffer[0]
        magnitude = np.linalg.norm(displacement)

        return displacement, magnitude

    def is_swipe(self, axis='x', direction=1, threshold=0.3, min_speed=0.5):
        """
        Detect if motion is a swipe along a specific axis.

        Args:
            axis: 'x', 'y', or 'z' - which axis to check
            direction: 1 for positive direction, -1 for negative
            threshold: Minimum displacement along axis (in normalized units)
            min_speed: Minimum speed required

        Returns:
            bool: True if motion matches swipe pattern
        """
        if len(self.position_buffer) < 5:
            return False

        displacement_vec, displacement_mag = self.get_displacement()
        velocity_vec, speed = self.get_velocity()

        # Check speed threshold
        if speed < min_speed:
            return False

        # Check displacement along specified axis
        axis_idx = {'x': 0, 'y': 1, 'z': 2}[axis]
        axis_displacement = displacement_vec[axis_idx]

        # Check if displacement is in correct direction and exceeds threshold
        if direction > 0:
            return axis_displacement > threshold
        else:
            return axis_displacement < -threshold

    def is_stationary(self, threshold=0.05):
        """
        Check if hand is relatively stationary.

        Args:
            threshold: Maximum displacement to be considered stationary

        Returns:
            bool: True if hand hasn't moved much
        """
        if len(self.position_buffer) < 2:
            return True

        _, displacement_mag = self.get_displacement()
        return displacement_mag < threshold

    def get_path_smoothness(self):
        """
        Calculate path smoothness (ratio of displacement to total distance).

        Returns:
            float: Smoothness value [0-1], where 1 is perfectly straight
        """
        if len(self.position_buffer) < 2:
            return 1.0

        total_dist = self.get_total_distance()
        _, displacement_mag = self.get_displacement()

        if total_dist > 1e-6:
            return displacement_mag / total_dist

        return 1.0

    def detect_clench(self, initial_openness, current_openness, threshold=0.5):
        """
        Detect clenching motion (hand closing into a fist).

        Args:
            initial_openness: Measure of how open hand was at start (e.g., finger spread)
            current_openness: Current measure of openness
            threshold: Minimum reduction in openness to detect clench

        Returns:
            bool: True if clench detected
        """
        reduction = initial_openness - current_openness
        return reduction > threshold

    @property
    def has_data(self):
        """Check if tracker has sufficient data"""
        return len(self.position_buffer) > 0

    @property
    def frame_count(self):
        """Get number of frames in buffer"""
        return len(self.position_buffer)
