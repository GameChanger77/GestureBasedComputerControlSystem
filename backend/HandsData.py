import numpy as np
from backend.LandmarkSmoother import LandmarkSmoother


class HandsData:
    """
    Container for hand landmark data with easy dot notation access.

    Handles smoothing and normalization of hand landmarks internally.
    Use the from_detection_result() factory method to create instances from MediaPipe data.
    """

    # Class-level smoother shared across all HandsData instances
    _smoother = None

    @classmethod
    def _get_smoother(cls):
        """Get or create the class-level smoother instance"""
        if cls._smoother is None:
            cls._smoother = LandmarkSmoother()
        return cls._smoother

    @staticmethod
    def _normalize_dominant_hand(dominant_hand):
        normalized = str(dominant_hand or "right").strip().lower()
        return "left" if normalized == "left" else "right"

    class FingerTips:
        """Container for fingertip positions with dot notation access"""

        def __init__(self, thumb, index, middle, ring, pinky):
            self.thumb = thumb
            self.index = index
            self.middle = middle
            self.ring = ring
            self.pinky = pinky

    class Finger:
        """Container for a single finger with joints and tip access"""

        def __init__(self, joints):
            """
            Args:
                joints: List of joint positions (4 joints, excluding wrist)
            """
            self.joints = joints

        def __getitem__(self, index):
            """Allow array-style access: finger[0], finger[1], etc."""
            return self.joints[index] if 0 <= index < len(self.joints) else None

        def __len__(self):
            """Return number of joints"""
            return len(self.joints)

        def __iter__(self):
            """Allow iteration over joints"""
            return iter(self.joints)

        @property
        def tip(self):
            """Get the fingertip (last joint)"""
            return self.joints[3] if len(self.joints) > 3 else None

        @property
        def base(self):
            """Get the base joint (first joint after wrist)"""
            return self.joints[0] if len(self.joints) > 0 else None

    class Hand:
        def __init__(self, landmarks_array):
            """
            Args:
                landmarks_array: Numpy array of shape (21, 3) in MediaPipe landmark order
            """
            if landmarks_array is not None and len(landmarks_array) >= 21:
                self._landmarks = landmarks_array
                self._wrist = landmarks_array[0]
                self.thumb = HandsData.Finger(landmarks_array[1:5])
                self.index = HandsData.Finger(landmarks_array[5:9])
                self.middle = HandsData.Finger(landmarks_array[9:13])
                self.ring = HandsData.Finger(landmarks_array[13:17])
                self.pinky = HandsData.Finger(landmarks_array[17:21])
            else:
                self._landmarks = None
                self._wrist = None
                self.thumb = HandsData.Finger([])
                self.index = HandsData.Finger([])
                self.middle = HandsData.Finger([])
                self.ring = HandsData.Finger([])
                self.pinky = HandsData.Finger([])

        @property
        def exists(self):
            """Check if this hand has any landmarks"""
            return self._wrist is not None

        @property
        def wrist(self):
            """Get wrist position"""
            return self._wrist

        @property
        def tip(self):
            """Get all fingertips with dot notation access"""
            return HandsData.FingerTips(
                self.thumb.tip,
                self.index.tip,
                self.middle.tip,
                self.ring.tip,
                self.pinky.tip
            )

        def get_fingertip(self, finger_name):
            """Safely get a fingertip by name (legacy method for backward compatibility)"""
            finger = getattr(self, finger_name, None)
            return finger.tip if finger else None

    class CoordinateSpace:
        def __init__(self, hands_dict, dominant_hand="right"):
            """
            Args:
                hands_dict: Dict like {'Left': np.ndarray(21,3), 'Right': np.ndarray(21,3)}
            """
            self._dominant_attr = HandsData._normalize_dominant_hand(dominant_hand)
            self.left = HandsData.Hand(hands_dict.get('Left'))
            self.right = HandsData.Hand(hands_dict.get('Right'))

        @property
        def has_left(self):
            """Check if left hand is detected"""
            return self.left.exists

        @property
        def has_right(self):
            """Check if right hand is detected"""
            return self.right.exists

        @property
        def dominant(self):
            """Return the configured dominant hand for this coordinate space."""
            return getattr(self, self._dominant_attr)

        @property
        def has_dominant(self):
            """Check if the configured dominant hand is detected."""
            return self.dominant.exists

        def get(self, hand_label):
            """Resolve a hand by logical label."""
            normalized = str(hand_label or "").strip().lower()
            if normalized == "left":
                return self.left
            if normalized == "right":
                return self.right
            if normalized == "dominant":
                return self.dominant
            return None

    def __init__(self, wrist_dict, camera_dict, dominant_hand="right"):
        """
        Args:
            wrist_dict: Wrist-relative normalized hand data
            camera_dict: Camera-relative hand data
        """
        self.dominant_hand = self._normalize_dominant_hand(dominant_hand)
        self.wrist = self.CoordinateSpace(wrist_dict, dominant_hand=self.dominant_hand)
        self.camera = self.CoordinateSpace(camera_dict, dominant_hand=self.dominant_hand)

    @classmethod
    def from_detection_result(cls, detection_result, dominant_hand="right"):
        """
        Factory method to create HandsData from MediaPipe detection result.

        Single-pass conversion:
        1. Extract landmarks as numpy arrays
        2. Smooth arrays (vectorized)
        3. Normalize arrays (vectorized)
        4. Store arrays directly for lightweight hand/finger views

        Args:
            detection_result: MediaPipe hand detection result
            dominant_hand: Configured dominant hand ("left" or "right")

        Returns:
            HandsData: Fully processed hand data with smoothed coordinates
        """
        smoother = cls._get_smoother()
        camera_data = {}
        wrist_data = {}
        dominant_hand = cls._normalize_dominant_hand(dominant_hand)
        dominant_label = "Left" if dominant_hand == "left" else "Right"

        # Process each detected hand
        if detection_result.hand_landmarks and detection_result.handedness:
            for hand_landmarks, handedness in zip(detection_result.hand_landmarks, detection_result.handedness):
                hand_label = handedness[0].category_name

                if hand_label != dominant_label:
                    continue
                if dominant_label in camera_data:
                    continue

                # Extract to a contiguous (21, 3) array with minimal intermediate allocations.
                raw_array = np.fromiter(
                    (coord for lm in hand_landmarks for coord in (lm.x, lm.y, lm.z)),
                    dtype=np.float32,
                    count=63,
                ).reshape(21, 3)

                # Smooth the array (vectorized operation)
                smoothed_array = smoother.smooth_hand(hand_label, raw_array)

                # Normalize for wrist-relative coordinates.
                wrist_pos = smoothed_array[0]
                middle_mcp = smoothed_array[9]  # Middle finger MCP joint
                dx = float(middle_mcp[0] - wrist_pos[0])
                dy = float(middle_mcp[1] - wrist_pos[1])
                dz = float(middle_mcp[2] - wrist_pos[2])
                hand_size = (dx * dx + dy * dy + dz * dz) ** 0.5
                if hand_size < 1e-6:
                    hand_size = 1e-6

                normalized_array = (smoothed_array - wrist_pos) / hand_size

                # Store arrays directly; Hand/Finger accessors expose the same high-level shape.
                camera_data[hand_label] = smoothed_array
                wrist_data[hand_label] = normalized_array

                if hand_label == dominant_label:
                    break

        # Return final HandsData
        return cls(wrist_data, camera_data, dominant_hand=dominant_hand)
