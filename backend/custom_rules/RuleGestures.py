from __future__ import annotations

from typing import Any, Dict, Optional

from backend.HandsData import HandsData
from backend.custom_rules.ConditionEvaluator import ConditionEvaluator
from backend.gestures.GestureRecognizer import SnapshotGestureRecognizer, ContinuousGestureRecognizer
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
        """
        Args:
            screen_width/screen_height: Needed for camera_to_screen conversion
            config: GestureConfig (used for screen_safe_margin)
            evaluator: ConditionEvaluator instance
            rule: The JSON rule dict for this gesture
        """
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.config = config
        self.evaluator = evaluator
        self.rule = rule

    def _pick_hand(self, hands_data: HandsData) -> Optional[str]:
        """
        Choose which hand label to evaluate for this gesture.

        Returns:
            "left" or "right" if available, else None
        """
        hand = self.rule.get("hand", "right")

        if hand == "right":
            return "right" if hands_data.wrist.has_right and hands_data.camera.has_right else None
        if hand == "left":
            return "left" if hands_data.wrist.has_left and hands_data.camera.has_left else None

        # either: prefer right then left (deterministic default)
        if hands_data.wrist.has_right and hands_data.camera.has_right:
            return "right"
        if hands_data.wrist.has_left and hands_data.camera.has_left:
            return "left"
        return None

    def _build_action_data(self, hands_data: HandsData, hand_label: str):
        """
        Build the data needed to execute this gesture's action.

        For screen actions (mouse_move, clicks):
        - Resolve "at" landmark in camera space (0..1 coords)
        - Convert to screen pixels with camera_to_screen()

        Returns:
            tuple describing action and parameters (action_type, ...)
        """
        action_spec = self.rule["action"]
        a_type = action_spec["type"]
        params = action_spec.get("params", {})

        safe_margin = int(self.config.get("screen_safe_margin", 50))

        # Mouse actions that need a screen coordinate target
        if a_type in ("left_click", "right_click", "mouse_move"):
            at = params.get("at", "index.tip")       # e.g., "index.tip"
            space = params.get("space", "camera")    # must be camera for screen mapping
            if space != "camera":
                # Keep behavior consistent with existing gestures:
                # screen-mapping uses camera coords, not wrist coords.
                return None

            hand_camera = hands_data.camera.right if hand_label == "right" else hands_data.camera.left
            finger_name, which = at.split(".")  # "index", "tip"
            finger = getattr(hand_camera, finger_name, None)
            if finger is None:
                return None

            pt = getattr(finger, which, None)
            if pt is None:
                return None

            sx, sy = camera_to_screen(pt, self.screen_width, self.screen_height, safe_margin=safe_margin)
            return (a_type, sx, sy)

        # Scroll uses integer deltas, no landmark needed
        if a_type == "scroll":
            dx = int(params.get("delta_x", 0))
            dy = int(params.get("delta_y", 0))
            return (a_type, dx, dy)

        # Extend later for keyboard/hotkeys (kept minimal right now)
        return (a_type, None)

    def _execute(self, data):
        """
        Execute the action using the Action API.

        Args:
            data: output of _build_action_data()
        """
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
        """
        Returns:
            tuple: (detected, action_data)
        """
        hand_label = self._pick_hand(hands_data)
        if hand_label is None:
            return False, None

        ok = self.evaluator.eval_all(hands_data, hand_label, self.rule["conditions"])
        if not ok:
            return False, None

        return True, self._build_action_data(hands_data, hand_label)

    def execute_action(self, data):
        """Execute the configured action once per activation."""
        self._execute(data)


class RuleContinuousGesture(ContinuousGestureRecognizer, _RuleGestureBase):
    """
    Continuous (hold) gesture compiled from JSON.

    Activated when:
    - All JSON conditions evaluate True for pending_frames
    - Fires EVERY frame while held (ContinuousGestureRecognizer behavior)

    WARNING:
    - Avoid mapping click actions to continuous gestures or you'll spam clicks.
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
        """
        Returns:
            tuple: (detected, action_data)
        """
        hand_label = self._pick_hand(hands_data)
        if hand_label is None:
            return False, None

        ok = self.evaluator.eval_all(hands_data, hand_label, self.rule["conditions"])
        if not ok:
            return False, None

        return True, self._build_action_data(hands_data, hand_label)

    def execute_action(self, data):
        """Execute the configured action every frame while active."""
        self._execute(data)