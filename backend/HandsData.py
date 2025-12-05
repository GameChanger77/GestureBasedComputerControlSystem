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
    def _array_to_finger_structure(landmarks_array):
        """
        Convert flat landmark array (21x3) to finger structure dict.

        Args:
            landmarks_array: numpy array of shape (21, 3) with landmarks in MediaPipe order

        Returns:
            list: Finger structure [wrist+thumb, wrist+index, wrist+middle, wrist+ring, wrist+pinky]
        """
        # Convert to list of tuples for compatibility with existing structure
        landmarks = [tuple(lm) for lm in landmarks_array]

        return [
            [landmarks[0], landmarks[1], landmarks[2], landmarks[3], landmarks[4]],      # Wrist + Thumb
            [landmarks[0], landmarks[5], landmarks[6], landmarks[7], landmarks[8]],      # Wrist + Index
            [landmarks[0], landmarks[9], landmarks[10], landmarks[11], landmarks[12]],   # Wrist + Middle
            [landmarks[0], landmarks[13], landmarks[14], landmarks[15], landmarks[16]],  # Wrist + Ring
            [landmarks[0], landmarks[17], landmarks[18], landmarks[19], landmarks[20]]   # Wrist + Pinky
        ]

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
        def __init__(self, fingers):
            """
            Args:
                fingers: List of 5 finger landmark lists [thumb, index, middle, ring, pinky]
                         Each finger has wrist at index 0, which we'll extract
            """
            if fingers and len(fingers) > 0 and len(fingers[0]) > 0:
                self._wrist = fingers[0][0]  # Extract wrist from first finger
                # Store fingers without the wrist (indices 1-4 for each finger)
                self.thumb = HandsData.Finger(fingers[0][1:]) if len(fingers) > 0 else HandsData.Finger([])
                self.index = HandsData.Finger(fingers[1][1:]) if len(fingers) > 1 else HandsData.Finger([])
                self.middle = HandsData.Finger(fingers[2][1:]) if len(fingers) > 2 else HandsData.Finger([])
                self.ring = HandsData.Finger(fingers[3][1:]) if len(fingers) > 3 else HandsData.Finger([])
                self.pinky = HandsData.Finger(fingers[4][1:]) if len(fingers) > 4 else HandsData.Finger([])
            else:
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
        def __init__(self, hands_dict):
            """
            Args:
                hands_dict: Dict like {'Left': [...], 'Right': [...]}
            """
            self.left = HandsData.Hand(hands_dict.get('Left', []))
            self.right = HandsData.Hand(hands_dict.get('Right', []))

        @property
        def has_left(self):
            """Check if left hand is detected"""
            return self.left.exists

        @property
        def has_right(self):
            """Check if right hand is detected"""
            return self.right.exists

    def __init__(self, wrist_dict, camera_dict):
        """
        Args:
            wrist_dict: Wrist-relative normalized hand data
            camera_dict: Camera-relative hand data
        """
        self.wrist = self.CoordinateSpace(wrist_dict)
        self.camera = self.CoordinateSpace(camera_dict)

    @classmethod
    def from_detection_result(cls, detection_result):
        """
        Factory method to create HandsData from MediaPipe detection result.

        Single-pass conversion:
        1. Extract landmarks as numpy arrays
        2. Smooth arrays (vectorized)
        3. Normalize arrays (vectorized)
        4. Convert to finger structure ONCE

        Args:
            detection_result: MediaPipe hand detection result

        Returns:
            HandsData: Fully processed hand data with smoothed coordinates
        """
        smoother = cls._get_smoother()
        camera_data = {}
        wrist_data = {}

        # Process each detected hand
        if detection_result.hand_landmarks and detection_result.handedness:
            for hand_landmarks, handedness in zip(detection_result.hand_landmarks, detection_result.handedness):
                hand_label = handedness[0].category_name

                # Extract to numpy array (21x3) - single extraction from MediaPipe
                raw_array = np.array(
                    [(lm.x, lm.y, lm.z) for lm in hand_landmarks],
                    dtype=np.float32
                )

                # Smooth the array (vectorized operation)
                smoothed_array = smoother.smooth_hand(hand_label, raw_array)

                # Normalize for wrist-relative coordinates (vectorized operation)
                wrist_pos = smoothed_array[0]
                middle_mcp = smoothed_array[9]  # Middle finger MCP joint
                hand_size = np.linalg.norm(middle_mcp - wrist_pos)
                hand_size = max(hand_size, 1e-6)  # Avoid division by zero

                normalized_array = (smoothed_array - wrist_pos) / hand_size

                # Convert to finger structure once for each coordinate space
                camera_data[hand_label] = cls._array_to_finger_structure(smoothed_array)
                wrist_data[hand_label] = cls._array_to_finger_structure(normalized_array)

        # Return final HandsData
        return cls(wrist_data, camera_data)
