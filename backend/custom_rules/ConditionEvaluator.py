from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from backend.HandsData import HandsData
from backend.gestures.GestureUtils import (
    are_fingers_pinched,
    are_only_fingers_extended,
    get_pinch_distance,
    get_hand_openness,
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

        if op == "only_fingers_extended":
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