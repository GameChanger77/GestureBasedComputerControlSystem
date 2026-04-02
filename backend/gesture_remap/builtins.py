from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

from backend.gesture_remap.hand_rig import HandEditorAssetManifest
from backend.gesture_remap.override_store import GestureOverrideStore
from backend.gesture_remap.pose_templates import HandPoseTemplate, build_default_templates, build_preview_templates
from backend.gesture_remap.recognizers import (
    TemplateKeyboardModeEntryGesture,
    TemplateKeyboardModeExitGesture,
    TemplateLeftClickGesture,
    TemplateMoveMouseGesture,
    TemplateRightClickGesture,
    TemplateScrollGesture,
)
from backend.gesture_remap.rule_overrides import GestureRuleOverride
from backend.gesture_remap.rule_recognizers import (
    RuleKeyboardModeEntryGesture,
    RuleKeyboardModeExitGesture,
    RuleLeftClickGesture,
    RuleMoveMouseGesture,
    RuleRightClickGesture,
    RuleScrollGesture,
)
from backend.gestures.mouse_mode.LeftClickGesture import LeftClickGesture
from backend.gestures.mouse_mode.MoveMouseGesture import MoveMouseGesture
from backend.gestures.mouse_mode.RightClickGesture import RightClickGesture
from backend.gestures.mouse_mode.ScrollGesture import ScrollGesture
from backend.gestures.switch_mode.KeyboardModeEntryGesture import KeyboardModeEntryGesture
from backend.gestures.switch_mode.KeyboardModeExitGesture import KeyboardModeExitGesture


@dataclass(frozen=True)
class BuiltInGestureDefinition:
    id: str
    display_name: str
    mode_label: str
    conflict_group: str
    hand: str
    default_description: str
    preview_pose_template: HandPoseTemplate
    saved_pose_template: HandPoseTemplate
    default_rule_factory: Callable
    default_factory: Callable
    override_factory: Callable
    rule_override_factory: Callable
    section: str

    @property
    def default_pose_template(self) -> HandPoseTemplate:
        return self.saved_pose_template

    def build_default_rule_override(self, config_source) -> GestureRuleOverride:
        return self.default_rule_factory(config_source)


class BuiltInGestureRegistry:
    _definitions: Dict[str, BuiltInGestureDefinition] | None = None

    @classmethod
    def _build_definitions(cls) -> Dict[str, BuiltInGestureDefinition]:
        templates = build_default_templates()
        neutral_landmarks = HandEditorAssetManifest.load().neutral_landmarks
        preview_templates = {
            key: HandPoseTemplate.from_array(f"{template.name} (Neutral)", neutral_landmarks)
            for key, template in build_preview_templates().items()
        }

        def _mouse_common(strategizer):
            config = strategizer.config
            return {
                "screen_width": strategizer.screen_width,
                "screen_height": strategizer.screen_height,
                "finger_angle": config["finger_extension_angle"],
                "scroll_sens": config["scroll_sensitivity"],
                "pinch_thresh": config["pinch_threshold"],
                "mouse_pending": config["mouse_tracking_pending_frames"],
                "click_pending": config["click_pending_frames"],
                "scroll_pending": config["scroll_pending_frames"],
                "ending": config["ending_frames"],
                "mouse_min_delta_px": config.get("mouse_move_min_delta_px", 2),
                "mouse_cadence_ms": config.get("mouse_move_cadence_ms", 75),
            }

        def mouse_move_default(action, strategizer):
            p = _mouse_common(strategizer)
            return MoveMouseGesture(
                action,
                p["screen_width"],
                p["screen_height"],
                priority=1,
                extension_threshold=p["finger_angle"],
                pending_frames=p["mouse_pending"],
                ending_frames=p["ending"],
                min_delta_px=p["mouse_min_delta_px"],
                cadence_ms=p["mouse_cadence_ms"],
            )

        def mouse_move_override(action, strategizer, record):
            p = _mouse_common(strategizer)
            return TemplateMoveMouseGesture(
                action,
                p["screen_width"],
                p["screen_height"],
                priority=1,
                extension_threshold=p["finger_angle"],
                pending_frames=p["mouse_pending"],
                ending_frames=p["ending"],
                min_delta_px=p["mouse_min_delta_px"],
                cadence_ms=p["mouse_cadence_ms"],
                pose_template=record.pose_template,
                matcher_config=record.matcher_config,
            )

        def mouse_move_rule_override(action, strategizer, record):
            p = _mouse_common(strategizer)
            return RuleMoveMouseGesture(
                action,
                p["screen_width"],
                p["screen_height"],
                priority=1,
                extension_threshold=p["finger_angle"],
                pending_frames=record.rule_override.pending_frames,
                ending_frames=record.rule_override.ending_frames,
                min_delta_px=p["mouse_min_delta_px"],
                cadence_ms=p["mouse_cadence_ms"],
                rule_override=record.rule_override,
            )

        def left_click_default(action, strategizer):
            p = _mouse_common(strategizer)
            return LeftClickGesture(
                action,
                p["screen_width"],
                p["screen_height"],
                priority=10,
                pinch_threshold=p["pinch_thresh"],
                extension_threshold=p["finger_angle"],
                pending_frames=p["click_pending"],
                ending_frames=p["ending"],
            )

        def left_click_override(action, strategizer, record):
            p = _mouse_common(strategizer)
            return TemplateLeftClickGesture(
                action,
                p["screen_width"],
                p["screen_height"],
                priority=10,
                pinch_threshold=p["pinch_thresh"],
                extension_threshold=p["finger_angle"],
                pending_frames=p["click_pending"],
                ending_frames=p["ending"],
                pose_template=record.pose_template,
                matcher_config=record.matcher_config,
            )

        def left_click_rule_override(action, strategizer, record):
            p = _mouse_common(strategizer)
            return RuleLeftClickGesture(
                action,
                p["screen_width"],
                p["screen_height"],
                priority=10,
                pinch_threshold=p["pinch_thresh"],
                extension_threshold=p["finger_angle"],
                pending_frames=record.rule_override.pending_frames,
                ending_frames=record.rule_override.ending_frames,
                rule_override=record.rule_override,
            )

        def right_click_default(action, strategizer):
            p = _mouse_common(strategizer)
            return RightClickGesture(
                action,
                p["screen_width"],
                p["screen_height"],
                priority=10,
                pinch_threshold=p["pinch_thresh"],
                extension_threshold=p["finger_angle"],
                pending_frames=p["click_pending"],
                ending_frames=p["ending"],
            )

        def right_click_override(action, strategizer, record):
            p = _mouse_common(strategizer)
            return TemplateRightClickGesture(
                action,
                p["screen_width"],
                p["screen_height"],
                priority=10,
                pinch_threshold=p["pinch_thresh"],
                extension_threshold=p["finger_angle"],
                pending_frames=p["click_pending"],
                ending_frames=p["ending"],
                pose_template=record.pose_template,
                matcher_config=record.matcher_config,
            )

        def right_click_rule_override(action, strategizer, record):
            p = _mouse_common(strategizer)
            return RuleRightClickGesture(
                action,
                p["screen_width"],
                p["screen_height"],
                priority=10,
                pinch_threshold=p["pinch_thresh"],
                extension_threshold=p["finger_angle"],
                pending_frames=record.rule_override.pending_frames,
                ending_frames=record.rule_override.ending_frames,
                rule_override=record.rule_override,
            )

        def scroll_default(action, strategizer):
            p = _mouse_common(strategizer)
            return ScrollGesture(
                action,
                priority=5,
                scroll_sensitivity=p["scroll_sens"],
                extension_threshold=p["finger_angle"],
                pending_frames=p["scroll_pending"],
                ending_frames=p["ending"],
            )

        def scroll_override(action, strategizer, record):
            p = _mouse_common(strategizer)
            return TemplateScrollGesture(
                action,
                priority=5,
                scroll_sensitivity=p["scroll_sens"],
                extension_threshold=p["finger_angle"],
                pending_frames=p["scroll_pending"],
                ending_frames=p["ending"],
                pose_template=record.pose_template,
                matcher_config=record.matcher_config,
            )

        def scroll_rule_override(action, strategizer, record):
            p = _mouse_common(strategizer)
            return RuleScrollGesture(
                action,
                priority=5,
                scroll_sensitivity=p["scroll_sens"],
                extension_threshold=p["finger_angle"],
                pending_frames=record.rule_override.pending_frames,
                ending_frames=record.rule_override.ending_frames,
                rule_override=record.rule_override,
            )

        def switch_common(strategizer):
            config = strategizer.config
            return {
                "finger_angle": config["finger_extension_angle"],
                "entry_pending": config.get("keyboard_mode_entry_pending_frames", 6),
                "exit_pending": config.get("keyboard_mode_exit_pending_frames", 5),
                "exit_angle": config.get("keyboard_mode_exit_extension_angle", 150.0),
                "exit_max_openness": config.get("keyboard_mode_exit_max_openness", 0.16),
                "exit_max_extension": config.get("keyboard_mode_exit_max_extension_ratio", 0.90),
                "exit_max_avg_angle": config.get("keyboard_mode_exit_max_avg_finger_angle", 145.0),
                "ending": config["ending_frames"],
            }

        def switch_to_keyboard_default(action, strategizer):
            p = switch_common(strategizer)
            return KeyboardModeEntryGesture(
                action,
                strategizer=strategizer,
                priority=20,
                extension_threshold=p["finger_angle"],
                pending_frames=p["entry_pending"],
                ending_frames=p["ending"],
            )

        def switch_to_keyboard_override(action, strategizer, record):
            p = switch_common(strategizer)
            return TemplateKeyboardModeEntryGesture(
                action,
                strategizer=strategizer,
                priority=20,
                extension_threshold=p["finger_angle"],
                pending_frames=p["entry_pending"],
                ending_frames=p["ending"],
                pose_template=record.pose_template,
                matcher_config=record.matcher_config,
            )

        def switch_to_keyboard_rule_override(action, strategizer, record):
            p = switch_common(strategizer)
            return RuleKeyboardModeEntryGesture(
                action,
                strategizer=strategizer,
                priority=20,
                extension_threshold=p["finger_angle"],
                pending_frames=record.rule_override.pending_frames,
                ending_frames=record.rule_override.ending_frames,
                rule_override=record.rule_override,
            )

        def switch_to_mouse_default(action, strategizer):
            p = switch_common(strategizer)
            return KeyboardModeExitGesture(
                action,
                strategizer=strategizer,
                priority=20,
                pending_frames=p["exit_pending"],
                ending_frames=p["ending"],
                extension_threshold=p["exit_angle"],
                max_openness=p["exit_max_openness"],
                max_extension_ratio=p["exit_max_extension"],
                max_avg_finger_angle=p["exit_max_avg_angle"],
            )

        def switch_to_mouse_override(action, strategizer, record):
            p = switch_common(strategizer)
            return TemplateKeyboardModeExitGesture(
                action,
                strategizer=strategizer,
                priority=20,
                pending_frames=p["exit_pending"],
                ending_frames=p["ending"],
                extension_threshold=p["exit_angle"],
                max_openness=p["exit_max_openness"],
                max_extension_ratio=p["exit_max_extension"],
                max_avg_finger_angle=p["exit_max_avg_angle"],
                pose_template=record.pose_template,
                matcher_config=record.matcher_config,
            )

        def switch_to_mouse_rule_override(action, strategizer, record):
            p = switch_common(strategizer)
            return RuleKeyboardModeExitGesture(
                action,
                strategizer=strategizer,
                priority=20,
                pending_frames=record.rule_override.pending_frames,
                ending_frames=record.rule_override.ending_frames,
                extension_threshold=p["exit_angle"],
                max_openness=p["exit_max_openness"],
                max_extension_ratio=p["exit_max_extension"],
                max_avg_finger_angle=p["exit_max_avg_angle"],
                rule_override=record.rule_override,
            )

        def mouse_move_rule_defaults(config_source):
            return GestureRuleOverride(
                conditions=[
                    {
                        "op": "only_fingers_extended",
                        "fingers": ["index"],
                        "threshold_deg": float(config_source.get("finger_extension_angle", 155.0)),
                    }
                ],
                pending_frames=int(config_source.get("mouse_tracking_pending_frames", 1)),
                ending_frames=int(config_source.get("ending_frames", 2)),
            )

        def left_click_rule_defaults(config_source):
            return GestureRuleOverride(
                conditions=[
                    {
                        "op": "pinch_distance_lt",
                        "a": "thumb.tip",
                        "b": "middle.tip",
                        "value": float(config_source.get("pinch_threshold", 0.30)),
                        "space": "wrist",
                    }
                ],
                pending_frames=int(config_source.get("click_pending_frames", 3)),
                ending_frames=int(config_source.get("ending_frames", 2)),
            )

        def right_click_rule_defaults(config_source):
            return GestureRuleOverride(
                conditions=[
                    {
                        "op": "pinch_distance_lt",
                        "a": "thumb.tip",
                        "b": "ring.tip",
                        "value": float(config_source.get("pinch_threshold", 0.30)),
                        "space": "wrist",
                    }
                ],
                pending_frames=int(config_source.get("click_pending_frames", 3)),
                ending_frames=int(config_source.get("ending_frames", 2)),
            )

        def scroll_rule_defaults(config_source):
            return GestureRuleOverride(
                conditions=[
                    {
                        "op": "only_fingers_extended",
                        "fingers": ["index", "middle"],
                        "threshold_deg": float(config_source.get("finger_extension_angle", 155.0)),
                    }
                ],
                pending_frames=int(config_source.get("scroll_pending_frames", 2)),
                ending_frames=int(config_source.get("ending_frames", 2)),
            )

        def switch_to_keyboard_rule_defaults(config_source):
            return GestureRuleOverride(
                conditions=[
                    {
                        "op": "hand_fully_open",
                        "extension_threshold": float(config_source.get("finger_extension_angle", 155.0)),
                        "min_extended_fingers": 4,
                        "openness_threshold": 0.08,
                    }
                ],
                pending_frames=int(config_source.get("keyboard_mode_entry_pending_frames", 6)),
                ending_frames=int(config_source.get("ending_frames", 2)),
            )

        def switch_to_mouse_rule_defaults(config_source):
            return GestureRuleOverride(
                conditions=[
                    {
                        "op": "strict_fist",
                        "max_openness": float(config_source.get("keyboard_mode_exit_max_openness", 0.16)),
                        "max_extension_ratio": float(config_source.get("keyboard_mode_exit_max_extension_ratio", 0.90)),
                        "max_avg_finger_angle": float(config_source.get("keyboard_mode_exit_max_avg_finger_angle", 145.0)),
                    }
                ],
                pending_frames=int(config_source.get("keyboard_mode_exit_pending_frames", 5)),
                ending_frames=int(config_source.get("ending_frames", 2)),
            )

        definitions = [
            BuiltInGestureDefinition(
                id="mouse_move",
                display_name="Mouse Move",
                mode_label="Mouse",
                conflict_group="mouse",
                hand="right",
                default_description="Move the cursor while holding the mouse-move pose.",
                preview_pose_template=preview_templates["mouse_move"],
                saved_pose_template=templates["mouse_move"],
                default_rule_factory=mouse_move_rule_defaults,
                default_factory=mouse_move_default,
                override_factory=mouse_move_override,
                rule_override_factory=mouse_move_rule_override,
                section="mouse",
            ),
            BuiltInGestureDefinition(
                id="left_click",
                display_name="Left Click",
                mode_label="Mouse",
                conflict_group="mouse",
                hand="right",
                default_description="Single click on pose enter, hold to trigger a double click.",
                preview_pose_template=preview_templates["left_click"],
                saved_pose_template=templates["left_click"],
                default_rule_factory=left_click_rule_defaults,
                default_factory=left_click_default,
                override_factory=left_click_override,
                rule_override_factory=left_click_rule_override,
                section="mouse",
            ),
            BuiltInGestureDefinition(
                id="right_click",
                display_name="Right Click",
                mode_label="Mouse",
                conflict_group="mouse",
                hand="right",
                default_description="Right click once per pose enter.",
                preview_pose_template=preview_templates["right_click"],
                saved_pose_template=templates["right_click"],
                default_rule_factory=right_click_rule_defaults,
                default_factory=right_click_default,
                override_factory=right_click_override,
                rule_override_factory=right_click_rule_override,
                section="mouse",
            ),
            BuiltInGestureDefinition(
                id="scroll",
                display_name="Scroll",
                mode_label="Mouse",
                conflict_group="mouse",
                hand="right",
                default_description="Scroll while holding the scroll pose and moving the hand vertically.",
                preview_pose_template=preview_templates["scroll"],
                saved_pose_template=templates["scroll"],
                default_rule_factory=scroll_rule_defaults,
                default_factory=scroll_default,
                override_factory=scroll_override,
                rule_override_factory=scroll_rule_override,
                section="mouse",
            ),
            BuiltInGestureDefinition(
                id="switch_to_keyboard",
                display_name="Switch To Keyboard Mode",
                mode_label="Keyboard Switching",
                conflict_group="switch",
                hand="right",
                default_description="Enter keyboard mode from mouse mode.",
                preview_pose_template=preview_templates["switch_to_keyboard"],
                saved_pose_template=templates["switch_to_keyboard"],
                default_rule_factory=switch_to_keyboard_rule_defaults,
                default_factory=switch_to_keyboard_default,
                override_factory=switch_to_keyboard_override,
                rule_override_factory=switch_to_keyboard_rule_override,
                section="switch",
            ),
            BuiltInGestureDefinition(
                id="switch_to_mouse",
                display_name="Switch To Mouse Mode",
                mode_label="Keyboard Switching",
                conflict_group="switch",
                hand="right",
                default_description="Exit keyboard mode back to mouse mode.",
                preview_pose_template=preview_templates["switch_to_mouse"],
                saved_pose_template=templates["switch_to_mouse"],
                default_rule_factory=switch_to_mouse_rule_defaults,
                default_factory=switch_to_mouse_default,
                override_factory=switch_to_mouse_override,
                rule_override_factory=switch_to_mouse_rule_override,
                section="switch",
            ),
        ]
        return {definition.id: definition for definition in definitions}

    @classmethod
    def _ensure_definitions(cls):
        if cls._definitions is None:
            cls._definitions = cls._build_definitions()

    @classmethod
    def all(cls) -> List[BuiltInGestureDefinition]:
        cls._ensure_definitions()
        return list(cls._definitions.values())

    @classmethod
    def get(cls, gesture_id: str) -> BuiltInGestureDefinition:
        cls._ensure_definitions()
        return cls._definitions[gesture_id]

    @classmethod
    def list_options(cls) -> list[dict]:
        return [
            {
                "id": definition.id,
                "display_name": definition.display_name,
                "mode_label": definition.mode_label,
                "description": definition.default_description,
            }
            for definition in cls.all()
        ]

    @classmethod
    def build_runtime_gesture(cls, gesture_id: str, strategizer, override_store: GestureOverrideStore):
        definition = cls.get(gesture_id)
        record = override_store.get(gesture_id) if override_store else None
        if record and record.enabled:
            if record.is_rule_override and record.rule_override is not None:
                return definition.rule_override_factory(strategizer.action, strategizer, record)
            if record.is_point_override:
                return definition.override_factory(strategizer.action, strategizer, record)
        return definition.default_factory(strategizer.action, strategizer)
