from __future__ import annotations

from backend.custom_rules.ConditionEvaluator import ConditionEvaluator
from backend.gesture_remap.pose_templates import hand_to_landmark_array, match_live_pose
from backend.gestures.GestureRecognizer import SnapshotGestureRecognizer


class _BaseMacroTriggerRecognizer(SnapshotGestureRecognizer):
    consumes_events = False

    def __init__(self, action, *, name: str, action_steps, priority: int, pending_frames: int, ending_frames: int):
        super().__init__(action, priority=priority, pending_frames=pending_frames, ending_frames=ending_frames)
        self.name = name
        self.action_steps = list(action_steps)

    def execute_action(self, data):
        self.action.execute_macro_steps(self.action_steps)


class PointMacroTriggerRecognizer(_BaseMacroTriggerRecognizer):
    def __init__(self, action, *, name: str, trigger, action_steps, priority: int = 30, pending_frames: int = 3, ending_frames: int = 2):
        super().__init__(
            action,
            name=name,
            action_steps=action_steps,
            priority=priority,
            pending_frames=pending_frames,
            ending_frames=ending_frames,
        )
        self.trigger = trigger

    def _matching_hands(self, hands_data):
        if self.trigger.hand in {"right", "either"} and hands_data.wrist.has_right:
            yield hands_data.wrist.right
        if self.trigger.hand in {"left", "either"} and hands_data.wrist.has_left:
            yield hands_data.wrist.left

    def detect_gesture(self, hands_data):
        for hand in self._matching_hands(hands_data):
            landmarks = hand_to_landmark_array(hand)
            if landmarks is None:
                continue
            was_active = bool(getattr(self, "is_active", False))
            result = match_live_pose(
                self.trigger.pose_template,
                landmarks,
                config=self.trigger.matcher_config,
                was_active=was_active,
            )
            if result.matched:
                return True, None
        return False, None


class RuleMacroTriggerRecognizer(_BaseMacroTriggerRecognizer):
    def __init__(self, action, *, name: str, trigger, action_steps, priority: int = 30):
        super().__init__(
            action,
            name=name,
            action_steps=action_steps,
            priority=priority,
            pending_frames=trigger.rule_override.pending_frames,
            ending_frames=trigger.rule_override.ending_frames,
        )
        self.trigger = trigger
        self.evaluator = ConditionEvaluator()

    def _candidate_hands(self):
        if self.trigger.hand == "either":
            return ("right", "left")
        return (self.trigger.hand,)

    def detect_gesture(self, hands_data):
        for hand_label in self._candidate_hands():
            if self.evaluator.eval_all(hands_data, hand_label, self.trigger.rule_override.conditions):
                return True, None
        return False, None
