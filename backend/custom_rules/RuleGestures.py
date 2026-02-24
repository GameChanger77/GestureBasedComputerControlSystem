from __future__ import annotations

from typing import Any, Dict, Optional

from backend.HandsData import HandsData
from backend.custom_rules.ConditionEvaluator import ConditionEvaluator
from backend.gestures.GestureRecognizer import SnapshotGestureRecognizer, ContinuousGestureRecognizer
from backend.gestures.GestureUtils import camera_to_screen


class _RuleGestureBase:
    def __init__(self, screen_width: int, screen_height: int, config, evaluator: ConditionEvaluator, rule: Dict[str, Any]):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.config = config
        self.evaluator = evaluator
        self.rule = rule

    def _pick_hand(self, hands_data: HandsData) -> Optional[str]:
        hand = self.rule.get("hand", "right")
        if hand == "right":
            return "right" if hands_data.wrist.has_right and hands_data.camera.has_right else None
        if hand == "left":
            return "left" if hands_data.wrist.has_left and hands_data.camera.has_left else None
        # either: prefer right then left
        if hands_data.wrist.has_right and hands_data.camera.has_right:
            return "right"
        if hands_data.wrist.has_left and hands_data.camera.has_left:
            return "left"
        return None

    def _build_action_data(self, hands_data: HandsData, hand_label: str):
        action_spec = self.rule["action"]
        a_type = action_spec["type"]
        params = action_spec.get("params", {})

        safe_margin = int(self.config.get("screen_safe_margin", 50))

        if a_type in ("left_click", "right_click", "mouse_move"):
            at = params.get("at", "index.tip")
            space = params.get("space", "camera")
            if space != "camera":
                # For screen-space actions we should use camera coords like your existing gestures do
                return None

            hand_camera = hands_data.camera.right if hand_label == "right" else hands_data.camera.left
            finger_name, which = at.split(".")
            finger = getattr(hand_camera, finger_name, None)
            if finger is None:
                return None

            pt = getattr(finger, which, None)
            if pt is None:
                return None

            sx, sy = camera_to_screen(pt, self.screen_width, self.screen_height, safe_margin=safe_margin)
            return (a_type, sx, sy)

        if a_type == "scroll":
            dx = int(params.get("delta_x", 0))
            dy = int(params.get("delta_y", 0))
            return (a_type, dx, dy)

        # You can extend later (keyboard/hotkey), but keep minimal for now
        return (a_type, None)

    def _execute(self, data):
        if not data:
            return
        a_type = data[0]

        if a_type == "left_click":
            _, x, y = data
            self.action.left_click(x, y)
        elif a_type == "right_click":
            _, x, y = data
            self.action.right_click(x, y)
        elif a_type == "mouse_move":
            _, x, y = data
            self.action.move_cursor(x, y)
        elif a_type == "scroll":
            _, dx, dy = data
            self.action.scroll(delta_x=dx, delta_y=dy)


class RuleSnapshotGesture(SnapshotGestureRecognizer, _RuleGestureBase):
    def __init__(self, action, screen_width, screen_height, config, evaluator, rule, pending_frames, ending_frames):
        SnapshotGestureRecognizer.__init__(self, action, priority=int(rule["priority"]),
                                          pending_frames=pending_frames, ending_frames=ending_frames)
        _RuleGestureBase.__init__(self, screen_width, screen_height, config, evaluator, rule)

    def detect_gesture(self, hands_data: HandsData):
        hand_label = self._pick_hand(hands_data)
        if hand_label is None:
            return False, None

        ok = self.evaluator.eval_all(hands_data, hand_label, self.rule["conditions"])
        if not ok:
            return False, None

        return True, self._build_action_data(hands_data, hand_label)

    def execute_action(self, data):
        self._execute(data)


class RuleContinuousGesture(ContinuousGestureRecognizer, _RuleGestureBase):
    def __init__(self, action, screen_width, screen_height, config, evaluator, rule, pending_frames, ending_frames):
        ContinuousGestureRecognizer.__init__(self, action, priority=int(rule["priority"]),
                                            pending_frames=pending_frames, ending_frames=ending_frames)
        _RuleGestureBase.__init__(self, screen_width, screen_height, config, evaluator, rule)

    def detect_gesture(self, hands_data: HandsData):
        hand_label = self._pick_hand(hands_data)
        if hand_label is None:
            return False, None

        ok = self.evaluator.eval_all(hands_data, hand_label, self.rule["conditions"])
        if not ok:
            return False, None

        return True, self._build_action_data(hands_data, hand_label)

    def execute_action(self, data):
        # IMPORTANT: don’t put click actions in continuous rules or you’ll spam clicks.
        self._execute(data)