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

    Supported ops (minimal set to ship "custom pose gestures"):
      - finger_extended
      - only_fingers_extended
      - pinch_distance_lt / pinch_distance_gt
      - hand_openness_gt / hand_openness_lt
      - hand_exists
      - hand_count_eq
    """

    def eval_all(self, hands_data: HandsData, hand_label: str, conditions: list[Dict[str, Any]]) -> bool:
        for cond in conditions:
            if not self.eval_one(hands_data, hand_label, cond):
                return False
        return True

    def eval_one(self, hands_data: HandsData, hand_label: str, cond: Dict[str, Any]) -> bool:
        op = cond.get("op")

        if op == "hand_exists":
            # cond.hand optional; defaults to current hand_label
            target = cond.get("hand", hand_label)
            return self._hand_exists(hands_data, target)

        if op == "hand_count_eq":
            target = int(cond.get("value", 0))
            count = int(hands_data.wrist.has_left) + int(hands_data.wrist.has_right)
            return count == target

        if op == "finger_extended":
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
            fingers = cond.get("fingers", [])
            thr = float(cond.get("threshold_deg", 155.0))

            hand = self._get_hand(hands_data.wrist, hand_label)
            if hand is None or not hand.exists:
                return False

            return are_only_fingers_extended(hand, fingers, thr)

        if op in ("pinch_distance_lt", "pinch_distance_gt"):
            space = cond.get("space", "wrist")
            a = self._resolve_point(hands_data, hand_label, space, cond.get("a"))
            b = self._resolve_point(hands_data, hand_label, space, cond.get("b"))
            if a is None or b is None:
                return False

            thresh = float(cond.get("value"))

            if op == "pinch_distance_lt":
                return are_fingers_pinched(a, b, thresh)
            else:
                return get_pinch_distance(a, b) > thresh

        if op in ("hand_openness_gt", "hand_openness_lt"):
            space = cond.get("space", "wrist")  # openness should use wrist space typically
            hand = self._get_hand(hands_data.wrist if space == "wrist" else hands_data.camera, hand_label)
            if hand is None or not hand.exists:
                return False
            val = float(cond.get("value"))
            openness = float(get_hand_openness(hand))
            return openness > val if op == "hand_openness_gt" else openness < val

        raise ValueError(f"Unknown condition op: {op}")

    def _hand_exists(self, hands_data: HandsData, hand_label: str) -> bool:
        if hand_label == "left":
            return hands_data.wrist.has_left and hands_data.camera.has_left
        if hand_label == "right":
            return hands_data.wrist.has_right and hands_data.camera.has_right
        # either
        return (hands_data.wrist.has_right and hands_data.camera.has_right) or \
               (hands_data.wrist.has_left and hands_data.camera.has_left)

    def _get_hand(self, coord_space, hand_label: str):
        if hand_label == "left":
            return coord_space.left
        if hand_label == "right":
            return coord_space.right
        return None

    def _resolve_point(
        self, hands_data: HandsData, hand_label: str, space: str, token: Optional[str]
    ) -> Optional[Point3]:
        if not token:
            return None

        coord = hands_data.wrist if space == "wrist" else hands_data.camera
        hand = self._get_hand(coord, hand_label)
        if hand is None or not hand.exists:
            return None

        if token == "wrist":
            return hand.wrist

        # token like "index.tip"
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