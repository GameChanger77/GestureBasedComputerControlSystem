class HandsData:
    """Container for hand landmark data with easy dot notation access"""

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
