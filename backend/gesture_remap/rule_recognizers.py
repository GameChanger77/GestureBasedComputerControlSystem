from __future__ import annotations

from backend.custom_rules.ConditionEvaluator import ConditionEvaluator
from backend.gesture_remap.rule_overrides import GestureRuleOverride
from backend.gestures.GestureUtils import camera_to_screen
from backend.gestures.mouse_mode.LeftClickGesture import LeftClickGesture
from backend.gestures.mouse_mode.MoveMouseGesture import MoveMouseGesture
from backend.gestures.mouse_mode.RightClickGesture import RightClickGesture
from backend.gestures.mouse_mode.ScrollGesture import ScrollGesture
from backend.gestures.switch_mode.HotkeyModeEntryGesture import HotkeyModeEntryGesture
from backend.gestures.switch_mode.KeyboardModeEntryGesture import KeyboardModeEntryGesture
from backend.gestures.switch_mode.KeyboardModeExitGesture import KeyboardModeExitGesture


class _RuleConditionMixin:
    def _configure_rule_override(self, rule_override: GestureRuleOverride, hand_label: str = "dominant"):
        self.rule_override = rule_override
        self.rule_hand_label = hand_label
        self.rule_evaluator = ConditionEvaluator()

    def _matches_rule(self, hands_data) -> bool:
        return self.rule_evaluator.eval_all(
            hands_data,
            self.rule_hand_label,
            self.rule_override.conditions,
        )

    def _hand_spaces(self, hands_data):
        return hands_data.wrist.get(self.rule_hand_label), hands_data.camera.get(self.rule_hand_label)


class RuleMoveMouseGesture(_RuleConditionMixin, MoveMouseGesture):
    def __init__(self, *args, rule_override: GestureRuleOverride, hand_label: str = "dominant", **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_rule_override(rule_override, hand_label=hand_label)

    def detect_gesture(self, hands_data):
        hand_wrist, hand_camera = self._hand_spaces(hands_data)
        if not hand_wrist.exists or not hand_camera.exists:
            return False, None
        if not self._matches_rule(hands_data):
            return False, None

        index_tip = hand_camera.index.tip
        if index_tip is None:
            return False, None
        screen_x, screen_y = camera_to_screen(
            index_tip,
            self.screen_width,
            self.screen_height,
            side_deadzone=self.camera_side_deadzone,
            top_deadzone=self.camera_top_deadzone,
            bottom_deadzone=self.camera_bottom_deadzone,
        )
        return True, (screen_x, screen_y)


class RuleScrollGesture(_RuleConditionMixin, ScrollGesture):
    def __init__(self, *args, rule_override: GestureRuleOverride, hand_label: str = "dominant", **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_rule_override(rule_override, hand_label=hand_label)

    def detect_gesture(self, hands_data):
        hand_wrist, hand_camera = self._hand_spaces(hands_data)
        if not hand_wrist.exists or not hand_camera.exists:
            self._last_y_position = None
            return False, None
        if not self._matches_rule(hands_data):
            self._last_y_position = None
            return False, None

        index_tip = hand_camera.index.tip
        middle_tip = hand_camera.middle.tip
        if index_tip is None or middle_tip is None:
            self._last_y_position = None
            return False, None

        current_y = (index_tip[1] + middle_tip[1]) / 2.0
        scroll_delta_y = 0
        if self._last_y_position is not None:
            raw_delta = current_y - self._last_y_position
            scroll_delta_y = int(raw_delta * self.scroll_sensitivity)

        self._last_y_position = current_y
        return True, scroll_delta_y


class RuleLeftClickGesture(_RuleConditionMixin, LeftClickGesture):
    def __init__(self, *args, rule_override: GestureRuleOverride, hand_label: str = "dominant", **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_rule_override(rule_override, hand_label=hand_label)

    def detect_gesture(self, hands_data):
        hand_wrist, hand_camera = self._hand_spaces(hands_data)
        if not hand_wrist.exists or not hand_camera.exists:
            return False, None
        if not self._matches_rule(hands_data):
            return False, None

        index_tip = hand_camera.index.tip
        if index_tip is None:
            return False, None
        screen_x, screen_y = camera_to_screen(
            index_tip,
            self.screen_width,
            self.screen_height,
            side_deadzone=self.camera_side_deadzone,
            top_deadzone=self.camera_top_deadzone,
            bottom_deadzone=self.camera_bottom_deadzone,
        )
        return True, (screen_x, screen_y)


class RuleRightClickGesture(_RuleConditionMixin, RightClickGesture):
    def __init__(self, *args, rule_override: GestureRuleOverride, hand_label: str = "dominant", **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_rule_override(rule_override, hand_label=hand_label)

    def detect_gesture(self, hands_data):
        hand_wrist, hand_camera = self._hand_spaces(hands_data)
        if not hand_wrist.exists or not hand_camera.exists:
            return False, None
        if not self._matches_rule(hands_data):
            return False, None

        index_tip = hand_camera.index.tip
        if index_tip is None:
            return False, None
        screen_x, screen_y = camera_to_screen(
            index_tip,
            self.screen_width,
            self.screen_height,
            side_deadzone=self.camera_side_deadzone,
            top_deadzone=self.camera_top_deadzone,
            bottom_deadzone=self.camera_bottom_deadzone,
        )
        return True, (screen_x, screen_y)


class RuleKeyboardModeEntryGesture(_RuleConditionMixin, KeyboardModeEntryGesture):
    def __init__(self, *args, rule_override: GestureRuleOverride, hand_label: str = "dominant", **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_rule_override(rule_override, hand_label=hand_label)

    def detect_gesture(self, hands_data):
        if self.strategizer.current_mode.value not in ("mouse", "hotkey"):
            return False, None
        hand_wrist, _ = self._hand_spaces(hands_data)
        if not hand_wrist.exists:
            return False, None
        return self._matches_rule(hands_data), None


class RuleHotkeyModeEntryGesture(_RuleConditionMixin, HotkeyModeEntryGesture):
    def __init__(self, *args, rule_override: GestureRuleOverride, hand_label: str = "dominant", **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_rule_override(rule_override, hand_label=hand_label)

    def detect_gesture(self, hands_data):
        if self.strategizer.current_mode.value not in ("mouse", "keyboard"):
            return False, None
        hand_wrist, _ = self._hand_spaces(hands_data)
        if not hand_wrist.exists:
            return False, None
        return self._matches_rule(hands_data), None


class RuleKeyboardModeExitGesture(_RuleConditionMixin, KeyboardModeExitGesture):
    def __init__(self, *args, rule_override: GestureRuleOverride, hand_label: str = "dominant", **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_rule_override(rule_override, hand_label=hand_label)

    def detect_gesture(self, hands_data):
        if self.strategizer.current_mode.value not in ("keyboard", "hotkey"):
            return False, None
        hand_wrist, _ = self._hand_spaces(hands_data)
        if not hand_wrist.exists:
            return False, None
        return self._matches_rule(hands_data), None
