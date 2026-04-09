from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from backend.HandsData import HandsData
from backend.gestures.GestureUtils import (
    are_fingers_pinched,
    are_only_fingers_extended,
    get_pinch_distance,
    get_hand_openness,
    is_hand_fully_open,
    is_finger_extended,
)

Point3 = Tuple[float, float, float]


class ConditionEvaluator:
    """
    Evaluates JSON "conditions" against HandsData.

    Purpose:
    - Custom gestures are authored in JSON, not Python.
    - Each JSON gesture has a list of boolean "conditions".
    - This class checks those conditions against the current frame.

    Supported ops (current minimal set):
    - finger_extended:
        { "op": "finger_extended", "finger": "index", "value": true, "threshold_deg": 155 }
    - only_fingers_extended:
        { "op": "only_fingers_extended", "fingers": ["index","middle"], "threshold_deg": 155 }
    - pinch_distance_lt / pinch_distance_gt:
        { "op": "pinch_distance_lt", "a": "thumb.tip", "b": "index.tip", "value": 0.13, "space": "wrist" }
    - hand_openness_gt / hand_openness_lt:
        { "op": "hand_openness_gt", "value": 0.4, "space": "wrist" }
    - hand_exists:
        { "op": "hand_exists", "hand": "right" }    # hand optional; defaults to current hand
    - hand_count_eq:
        { "op": "hand_count_eq", "value": 1 }

    Notes:
    - Most "pose" conditions should use wrist space, because wrist space is scale-normalized.
    - Actions that map to screen coordinates should use camera space (handled later in RuleGestures).
    """
    _STRICT_FIST_MAX_THUMB_EXTENSION_RATIO = 0.98

    def eval_all(self, hands_data: HandsData, hand_label: str, conditions: list[Dict[str, Any]]) -> bool:
        """
        Evaluate a list of conditions (logical AND).

        Returns:
            bool: True if ALL conditions are satisfied this frame.
        """
        for cond in conditions:
            if not self.eval_one(hands_data, hand_label, cond):
                return False
        return True

    def eval_one(self, hands_data: HandsData, hand_label: str, cond: Dict[str, Any]) -> bool:
        """
        Evaluate a single JSON condition.

        Args:
            hands_data: Current frame hand landmarks (wrist + camera spaces)
            hand_label: "left" or "right" chosen for this gesture
            cond: JSON dict for one condition

        Returns:
            bool: True if this condition is satisfied.
        """
        op = cond.get("op")

        # -------------------------------
        # Hand existence / count guards
        # -------------------------------
        if op == "hand_exists":
            # cond.hand optional; defaults to current hand_label
            target = cond.get("hand", hand_label)
            return self._hand_exists(hands_data, target)

        if op == "hand_count_eq":
            target = int(cond.get("value", 0))
            count = int(hands_data.wrist.has_left) + int(hands_data.wrist.has_right)
            return count == target

        # -------------------------------
        # Finger state conditions
        # -------------------------------
        if op == "finger_extended":
            # Example:
            # { "op": "finger_extended", "finger": "middle", "value": false, "threshold_deg": 155 }
            finger_name = cond.get("finger")
            want = bool(cond.get("value", True))
            thr = float(cond.get("threshold_deg", 155.0))

            hand = self._get_hand(hands_data.wrist, hand_label)
            if hand is None or not hand.exists:
                return False

            finger = getattr(hand, finger_name, None)
            if finger is None:
                raise ValueError(f"Unknown finger '{finger_name}' in finger_extended")

            got = is_finger_extended(finger, threshold=thr)
            return got == want

        if op in {"only_fingers_extended", "only_fingers_extended.json"}:
            # Example:
            # { "op": "only_fingers_extended", "fingers": ["index"], "threshold_deg": 155 }
            fingers = cond.get("fingers", [])
            thr = float(cond.get("threshold_deg", 155.0))

            hand = self._get_hand(hands_data.wrist, hand_label)
            if hand is None or not hand.exists:
                return False

            return are_only_fingers_extended(hand, fingers, thr)

        # -------------------------------
        # Pinch distance conditions
        # -------------------------------
        if op in ("pinch_distance_lt", "pinch_distance_gt"):
            # Example:
            # { "op": "pinch_distance_lt", "a": "thumb.tip", "b": "index.tip", "value": 0.13, "space": "wrist" }
            space = cond.get("space", "wrist")
            a = self._resolve_point(hands_data, hand_label, space, cond.get("a"))
            b = self._resolve_point(hands_data, hand_label, space, cond.get("b"))
            if a is None or b is None:
                return False

            thresh = float(cond.get("value"))

            if op == "pinch_distance_lt":
                # Uses your optimized pinch helper
                return are_fingers_pinched(a, b, thresh)
            else:
                return get_pinch_distance(a, b) > thresh

        # -------------------------------
        # Hand openness conditions
        # -------------------------------
        if op in ("hand_openness_gt", "hand_openness_lt"):
            # Openness is typically best evaluated in wrist space (normalized).
            space = cond.get("space", "wrist")
            hand = self._get_hand(hands_data.wrist if space == "wrist" else hands_data.camera, hand_label)
            if hand is None or not hand.exists:
                return False

            val = float(cond.get("value"))
            openness = float(get_hand_openness(hand))
            return openness > val if op == "hand_openness_gt" else openness < val

        if op == "hand_fully_open":
            hand = self._get_hand(hands_data.wrist, hand_label)
            if hand is None or not hand.exists:
                return False
            return is_hand_fully_open(
                hand,
                extension_threshold=float(cond.get("extension_threshold", 155.0)),
                min_extended_fingers=int(cond.get("min_extended_fingers", 4)),
                openness_threshold=float(cond.get("openness_threshold", 0.08)),
                require_palm_facing_camera=bool(cond.get("require_palm_facing_camera", False)),
                min_palm_normal_z=float(cond.get("min_palm_normal_z", 0.35)),
            )

        if op == "strict_fist":
            hand = self._get_hand(hands_data.wrist, hand_label)
            if hand is None or not hand.exists:
                return False
            return self._is_strict_fist(
                hand,
                max_openness=float(cond.get("max_openness", 0.16)),
                max_extension_ratio=float(cond.get("max_extension_ratio", 0.90)),
                max_avg_finger_angle=float(cond.get("max_avg_finger_angle", 145.0)),
            )

        # Unknown op: fail fast with an error so JSON authors get actionable feedback.
        raise ValueError(f"Unknown condition op: {op}")

    # =========================================================
    # Helpers (hand selection + landmark resolution)
    # =========================================================

    def _hand_exists(self, hands_data: HandsData, hand_label: str) -> bool:
        """
        Checks whether a given hand exists in BOTH wrist and camera spaces.

        Returns:
            bool: True if the requested hand is detected.
        """
        if hand_label == "left":
            return hands_data.wrist.has_left and hands_data.camera.has_left
        if hand_label == "right":
            return hands_data.wrist.has_right and hands_data.camera.has_right
        # either
        return (hands_data.wrist.has_right and hands_data.camera.has_right) or \
               (hands_data.wrist.has_left and hands_data.camera.has_left)

    def _get_hand(self, coord_space, hand_label: str):
        """
        Select a specific Hand object from a coordinate space.

        Args:
            coord_space: hands_data.wrist or hands_data.camera
            hand_label: "left" or "right"

        Returns:
            Hand or None
        """
        if hand_label == "left":
            return coord_space.left
        if hand_label == "right":
            return coord_space.right
        return None

    def _resolve_point(
        self, hands_data: HandsData, hand_label: str, space: str, token: Optional[str]
    ) -> Optional[Point3]:
        """
        Resolve a landmark token into a 3D point (x,y,z).

        Supported tokens:
            - "wrist"
            - "<finger>.tip"   e.g., "index.tip"
            - "<finger>.base"  e.g., "middle.base"

        Args:
            space: "wrist" or "camera"
            token: landmark string

        Returns:
            tuple (x,y,z) or None if not available this frame
        """
        if not token:
            return None

        coord = hands_data.wrist if space == "wrist" else hands_data.camera
        hand = self._get_hand(coord, hand_label)
        if hand is None or not hand.exists:
            return None

        if token == "wrist":
            return hand.wrist

        parts = token.split(".")
        if len(parts) != 2:
            raise ValueError(f"Bad landmark token '{token}' (expected like 'index.tip')")

        finger_name, which = parts
        finger = getattr(hand, finger_name, None)
        if finger is None:
            raise ValueError(f"Unknown finger '{finger_name}' in landmark token '{token}'")

        if which == "tip":
            return finger.tip
        if which == "base":
            return finger.base

        raise ValueError(f"Unknown landmark selector '{which}' in '{token}'")

    def _is_strict_fist(
        self,
        hand,
        *,
        max_openness: float,
        max_extension_ratio: float,
        max_avg_finger_angle: float,
    ) -> bool:
        # Ignore thumb spread so resting it beside or in front of the fist does
        # not affect fist detection, but still reject a clearly straight thumb.
        openness = get_hand_openness(hand, include_thumb=False)
        if openness > max_openness:
            return False

        finger_extensions = [
            self._finger_extension(hand.index),
            self._finger_extension(hand.middle),
            self._finger_extension(hand.ring),
            self._finger_extension(hand.pinky),
        ]
        if max(finger_extensions) > max_extension_ratio:
            return False
        if self._finger_extension(hand.thumb) > self._STRICT_FIST_MAX_THUMB_EXTENSION_RATIO:
            return False

        finger_angles = [
            self._finger_angle(hand.index),
            self._finger_angle(hand.middle),
            self._finger_angle(hand.ring),
            self._finger_angle(hand.pinky),
        ]
        avg_angle = sum(finger_angles) / len(finger_angles)
        return avg_angle <= max_avg_finger_angle

    @staticmethod
    def _finger_extension(finger) -> float:
        if finger is None or len(finger.joints) < 4:
            return 0.0

        total_length = 0.0
        for idx in range(len(finger.joints) - 1):
            first = finger.joints[idx]
            second = finger.joints[idx + 1]
            dx = second[0] - first[0]
            dy = second[1] - first[1]
            dz = second[2] - first[2]
            total_length += (dx * dx + dy * dy + dz * dz) ** 0.5

        base = finger.joints[0]
        tip = finger.joints[-1]
        dx = tip[0] - base[0]
        dy = tip[1] - base[1]
        dz = tip[2] - base[2]
        straight_distance = (dx * dx + dy * dy + dz * dz) ** 0.5
        if total_length <= 1e-6:
            return 0.0
        return straight_distance / total_length

    @staticmethod
    def _finger_angle(finger) -> float:
        if finger is None or len(finger.joints) < 4:
            return 0.0

        import math

        angles = []
        for idx in range(1, len(finger.joints) - 1):
            prev_joint = finger.joints[idx - 1]
            joint = finger.joints[idx]
            next_joint = finger.joints[idx + 1]
            vx1 = prev_joint[0] - joint[0]
            vy1 = prev_joint[1] - joint[1]
            vz1 = prev_joint[2] - joint[2]
            vx2 = next_joint[0] - joint[0]
            vy2 = next_joint[1] - joint[1]
            vz2 = next_joint[2] - joint[2]
            mag1 = (vx1 * vx1 + vy1 * vy1 + vz1 * vz1) ** 0.5
            mag2 = (vx2 * vx2 + vy2 * vy2 + vz2 * vz2) ** 0.5
            if mag1 <= 1e-6 or mag2 <= 1e-6:
                continue
            cos_angle = ((vx1 * vx2) + (vy1 * vy2) + (vz1 * vz2)) / (mag1 * mag2)
            cos_angle = max(-1.0, min(1.0, cos_angle))
            angles.append(math.degrees(math.acos(cos_angle)))

        if not angles:
            return 0.0
        return sum(angles) / len(angles)
