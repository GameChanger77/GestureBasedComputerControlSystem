from __future__ import annotations

from typing import Any, Dict, Optional

from backend.HandsData import HandsData
from backend.custom_rules.ConditionEvaluator import ConditionEvaluator
from backend.gestures.GestureRecognizer import ContinuousGestureRecognizer, SnapshotGestureRecognizer
from backend.gestures.GestureUtils import camera_to_screen


class _RuleGestureBase:
    """
    Shared implementation for JSON-defined gestures.

    Responsibilities:
    - Choose which hand to use ("left", "right", "either")
    - Evaluate JSON conditions via ConditionEvaluator
    - Convert action targets (like "index.tip") to screen coordinates
    - Execute Action methods (left_click, right_click, move_cursor, scroll)
    """

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

        if hands_data.wrist.has_right and hands_data.camera.has_right:
            return "right"
        if hands_data.wrist.has_left and hands_data.camera.has_left:
            return "left"
        return None

    def _build_action_data(self, hands_data: HandsData, hand_label: str):
        """
        Build the data needed to execute this gesture's action.

        Supported top-level action types:
        - left_click
        - right_click
        - mouse_move
        - scroll
        """
        action_spec = self.rule["action"]
        a_type = action_spec["type"]
        params = action_spec.get("params", {})

        if a_type in ("left_click", "right_click", "mouse_move"):
            target = self._resolve_screen_target(hands_data, hand_label, params, allow_default_landmark=True)
            if target is None:
                return None
            sx, sy = target
            return (a_type, sx, sy)

        if a_type == "scroll":
            dx = int(params.get("delta_x", 0))
            dy = int(params.get("delta_y", 0))
            return (a_type, dx, dy)

        return (a_type, None)

    def _resolve_screen_target(
        self,
        hands_data: HandsData,
        hand_label: str,
        params: Dict[str, Any],
        *,
        allow_default_landmark: bool,
    ) -> Optional[tuple[int, int]]:
        """
        Resolve a target to absolute screen pixels.

        Supported targeting styles:
        1) normalized screen coords:
           { "screen_x": 0.5, "screen_y": 0.5 }
        2) absolute pixel coords:
           { "x": 960, "y": 540 }
        3) landmark in camera space:
           { "at": "index.tip", "space": "camera" }

        If allow_default_landmark=True and no explicit target is given,
        defaults to at="index.tip", space="camera" for backward compatibility.
        """
        if "screen_x" in params and "screen_y" in params:
            sx = int(float(params["screen_x"]) * self.screen_width)
            sy = int(float(params["screen_y"]) * self.screen_height)
            return sx, sy

        if "x" in params and "y" in params:
            return int(params["x"]), int(params["y"])

        if not allow_default_landmark and "at" not in params:
            return None

        at = params.get("at", "index.tip")
        space = params.get("space", "camera")
        if space != "camera":
            return None

        hand_camera = hands_data.camera.right if hand_label == "right" else hands_data.camera.left
        if hand_camera is None or not hand_camera.exists:
            return None

        finger_name, which = at.split(".")
        finger = getattr(hand_camera, finger_name, None)
        if finger is None:
            return None

        pt = getattr(finger, which, None)
        if pt is None:
            return None

        sx, sy = camera_to_screen(pt, self.screen_width, self.screen_height)
        return sx, sy

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
    """
    Snapshot (pose) gesture compiled from JSON.

    Activated when:
    - All JSON conditions evaluate True for pending_frames
    - Fires ONCE per activation (debounced by SnapshotGestureRecognizer)
    """

    def __init__(self, action, screen_width, screen_height, config, evaluator, rule, pending_frames, ending_frames):
        SnapshotGestureRecognizer.__init__(
            self,
            action,
            priority=int(rule["priority"]),
            pending_frames=pending_frames,
            ending_frames=ending_frames,
        )
        _RuleGestureBase.__init__(self, screen_width, screen_height, config, evaluator, rule)

    def detect_gesture(self, hands_data: HandsData):
        hand_label = self._pick_hand(hands_data)
        if hand_label is None:
            return False, None

        if not self.evaluator.eval_all(hands_data, hand_label, self.rule["conditions"]):
            return False, None

        return True, self._build_action_data(hands_data, hand_label)

    def execute_action(self, data):
        self._execute(data)


class RuleContinuousGesture(ContinuousGestureRecognizer, _RuleGestureBase):
    """
    Continuous (hold) gesture compiled from JSON.

    Activated when:
    - All JSON conditions evaluate True for pending_frames
    - Fires EVERY frame while held (ContinuousGestureRecognizer behavior)
    """

    def __init__(self, action, screen_width, screen_height, config, evaluator, rule, pending_frames, ending_frames):
        ContinuousGestureRecognizer.__init__(
            self,
            action,
            priority=int(rule["priority"]),
            pending_frames=pending_frames,
            ending_frames=ending_frames,
        )
        _RuleGestureBase.__init__(self, screen_width, screen_height, config, evaluator, rule)

    def detect_gesture(self, hands_data: HandsData):
        hand_label = self._pick_hand(hands_data)
        if hand_label is None:
            return False, None

        if not self.evaluator.eval_all(hands_data, hand_label, self.rule["conditions"]):
            return False, None

        return True, self._build_action_data(hands_data, hand_label)

    def execute_action(self, data):
        self._execute(data)
