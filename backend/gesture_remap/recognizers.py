from __future__ import annotations

from backend.gesture_remap.pose_templates import (
    HandPoseTemplate,
    PoseMatcherConfig,
    hand_to_landmark_array,
    match_live_pose,
)
from backend.gestures.GestureUtils import camera_to_screen
from backend.gestures.mouse_mode.LeftClickGesture import LeftClickGesture
from backend.gestures.mouse_mode.MoveMouseGesture import MoveMouseGesture
from backend.gestures.mouse_mode.RightClickGesture import RightClickGesture
from backend.gestures.mouse_mode.ScrollGesture import ScrollGesture
from backend.gestures.switch_mode.HotkeyModeEntryGesture import HotkeyModeEntryGesture
from backend.gestures.switch_mode.KeyboardModeEntryGesture import KeyboardModeEntryGesture
from backend.gestures.switch_mode.KeyboardModeExitGesture import KeyboardModeExitGesture


class _TemplatePoseMixin:
    def _configure_pose(self, pose_template: HandPoseTemplate, matcher_config: PoseMatcherConfig):
        self.pose_template = pose_template
        self.matcher_config = matcher_config

    def _matches_pose(self, hands_data):
        hand = hands_data.wrist.dominant
        landmarks = hand_to_landmark_array(hand)
        if landmarks is None:
            return False
        was_active = bool(getattr(self, "is_active", False))
        match_result = match_live_pose(
            self.pose_template,
            landmarks,
            config=self.matcher_config,
            was_active=was_active,
        )
        return match_result.matched


class TemplateMoveMouseGesture(_TemplatePoseMixin, MoveMouseGesture):
    def __init__(self, *args, pose_template: HandPoseTemplate, matcher_config: PoseMatcherConfig, **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_pose(pose_template, matcher_config)

    def detect_gesture(self, hands_data):
        if not self._matches_pose(hands_data):
            return False, None
        if not hands_data.camera.has_dominant:
            return False, None
        index_tip = hands_data.camera.dominant.index.tip
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


class TemplateScrollGesture(_TemplatePoseMixin, ScrollGesture):
    def __init__(self, *args, pose_template: HandPoseTemplate, matcher_config: PoseMatcherConfig, **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_pose(pose_template, matcher_config)

    def detect_gesture(self, hands_data):
        if not self._matches_pose(hands_data):
            self._last_y_position = None
            return False, None
        if not hands_data.camera.has_dominant:
            self._last_y_position = None
            return False, None
        index_tip = hands_data.camera.dominant.index.tip
        middle_tip = hands_data.camera.dominant.middle.tip
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


class TemplateLeftClickGesture(_TemplatePoseMixin, LeftClickGesture):
    def __init__(self, *args, pose_template: HandPoseTemplate, matcher_config: PoseMatcherConfig, **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_pose(pose_template, matcher_config)

    def detect_gesture(self, hands_data):
        if not self._matches_pose(hands_data):
            return False, None
        if not hands_data.camera.has_dominant:
            return False, None
        index_tip = hands_data.camera.dominant.index.tip
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


class TemplateRightClickGesture(_TemplatePoseMixin, RightClickGesture):
    def __init__(self, *args, pose_template: HandPoseTemplate, matcher_config: PoseMatcherConfig, **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_pose(pose_template, matcher_config)

    def detect_gesture(self, hands_data):
        if not self._matches_pose(hands_data):
            return False, None
        if not hands_data.camera.has_dominant:
            return False, None
        index_tip = hands_data.camera.dominant.index.tip
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


class TemplateKeyboardModeEntryGesture(_TemplatePoseMixin, KeyboardModeEntryGesture):
    def __init__(self, *args, pose_template: HandPoseTemplate, matcher_config: PoseMatcherConfig, **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_pose(pose_template, matcher_config)

    def detect_gesture(self, hands_data):
        if self.strategizer.current_mode.value not in ("mouse", "hotkey"):
            return False, None
        return self._matches_pose(hands_data), None


class TemplateHotkeyModeEntryGesture(_TemplatePoseMixin, HotkeyModeEntryGesture):
    def __init__(self, *args, pose_template: HandPoseTemplate, matcher_config: PoseMatcherConfig, **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_pose(pose_template, matcher_config)

    def detect_gesture(self, hands_data):
        if self.strategizer.current_mode.value not in ("mouse", "keyboard"):
            return False, None
        return self._matches_pose(hands_data), None


class TemplateKeyboardModeExitGesture(_TemplatePoseMixin, KeyboardModeExitGesture):
    def __init__(self, *args, pose_template: HandPoseTemplate, matcher_config: PoseMatcherConfig, **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_pose(pose_template, matcher_config)

    def detect_gesture(self, hands_data):
        if self.strategizer.current_mode.value not in ("keyboard", "hotkey"):
            return False, None
        return self._matches_pose(hands_data), None
