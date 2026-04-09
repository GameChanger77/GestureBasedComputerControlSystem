from __future__ import annotations

from backend.custom_rules.ConditionEvaluator import ConditionEvaluator
from backend.gesture_remap.pose_templates import hand_to_landmark_array, match_live_pose
from backend.gestures.GestureRecognizer import MotionGestureRecognizer, SnapshotGestureRecognizer


class _BaseMacroShortcutRecognizer:
    consumes_events = False

    def _configure_macro(self, *, name: str, shortcut_keys, priority: int):
        self.name = name
        self.shortcut_keys = list(shortcut_keys)
        self.priority = priority
        self.debug_name = name
        self.suppresses_lower_priorities_while_active = True

    def _fire_shortcut(self):
        self.action.tap_hotkey(self.shortcut_keys)


class _BaseSnapshotMacroRecognizer(_BaseMacroShortcutRecognizer, SnapshotGestureRecognizer):
    def __init__(self, action, *, name: str, shortcut_keys, priority: int, pending_frames: int, ending_frames: int):
        SnapshotGestureRecognizer.__init__(
            self,
            action,
            priority=priority,
            pending_frames=pending_frames,
            ending_frames=ending_frames,
        )
        self._configure_macro(name=name, shortcut_keys=shortcut_keys, priority=priority)

    def execute_action(self, _data):
        self._fire_shortcut()


class PointMacroTriggerRecognizer(_BaseSnapshotMacroRecognizer):
    def __init__(
        self,
        action,
        *,
        name: str,
        trigger,
        shortcut_keys,
        priority: int = 30,
        pending_frames: int = 3,
        ending_frames: int = 2,
    ):
        super().__init__(
            action,
            name=name,
            shortcut_keys=shortcut_keys,
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


class RuleMacroTriggerRecognizer(_BaseSnapshotMacroRecognizer):
    def __init__(self, action, *, name: str, trigger, shortcut_keys, priority: int = 30):
        super().__init__(
            action,
            name=name,
            shortcut_keys=shortcut_keys,
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


class SwipeMacroTriggerRecognizer(_BaseMacroShortcutRecognizer, MotionGestureRecognizer):
    def __init__(self, action, *, name: str, trigger, shortcut_keys, priority: int = 30):
        MotionGestureRecognizer.__init__(
            self,
            action,
            priority=priority,
            buffer_frames=max(12, int(trigger.swipe_config.timeout_frames)),
            start_confirm_frames=int(trigger.swipe_config.start_confirm_frames),
            timeout_frames=int(trigger.swipe_config.timeout_frames),
        )
        self._configure_macro(name=name, shortcut_keys=shortcut_keys, priority=priority)
        self.trigger = trigger
        self.evaluator = ConditionEvaluator()
        self._active_hand_label = None
        self._requires_rearm = False

    def _candidate_hands(self):
        if self.trigger.hand == "either":
            return ("right", "left")
        return (self.trigger.hand,)

    def _current_start_hand(self, hands_data):
        for hand_label in self._candidate_hands():
            if self.evaluator.eval_all(
                hands_data,
                hand_label,
                self.trigger.start_rule_override.conditions,
            ):
                return hand_label
        return None

    def _resolve_tracking_point(self, hands_data, hand_label: str):
        return self.evaluator._resolve_point(
            hands_data,
            hand_label,
            "camera",
            self.trigger.swipe_config.tracked_point,
        )

    def update(self, hands_data, frame_capture_ts_ns=None):
        if self._requires_rearm:
            if self._current_start_hand(hands_data) is not None:
                self._set_debug_frame(
                    detected=False,
                    should_trigger=False,
                    action_executed=False,
                    state=self.current_state,
                    note="Waiting for swipe rearm",
                )
                return False
            self._requires_rearm = False
            self._active_hand_label = None
        return super().update(hands_data, frame_capture_ts_ns=frame_capture_ts_ns)

    def detect_start_pose(self, hands_data):
        hand_label = self._current_start_hand(hands_data)
        if hand_label is None:
            if self.state_machine.is_idle:
                self._active_hand_label = None
            return False, None
        self._active_hand_label = hand_label
        return True, hand_label

    def detect_motion_in_progress(self, hands_data):
        hand_label = self._active_hand_label or self._current_start_hand(hands_data)
        if hand_label is None:
            return False, None
        tracking_point = self._resolve_tracking_point(hands_data, hand_label)
        if tracking_point is None:
            return False, None
        self._active_hand_label = hand_label
        return True, tracking_point

    def validate_motion_pattern(self):
        config = self.trigger.swipe_config
        axis = "x" if config.direction in {"left", "right"} else "y"
        direction = 1 if config.direction in {"right", "down"} else -1
        if not self.motion_tracker.is_swipe(
            axis=axis,
            direction=direction,
            threshold=float(config.min_displacement),
            min_speed=float(config.min_speed),
        ):
            return False, None
        if self.motion_tracker.get_path_smoothness() < float(config.min_smoothness):
            return False, None
        return True, None

    def execute_action(self, _data):
        self._fire_shortcut()
        self._requires_rearm = True
        self._active_hand_label = None
        self.motion_tracker.clear()
        self.state_machine.reset()

    def reset(self):
        super().reset()
        self._active_hand_label = None
