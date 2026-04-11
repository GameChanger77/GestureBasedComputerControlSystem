from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from backend.custom_rules.condition_catalog import LANDMARK_OPTIONS
from backend.gesture_remap.pose_templates import HandPoseTemplate, PoseMatcherConfig
from backend.gesture_remap.rule_overrides import (
    GestureRuleOverride,
    POINT_OVERRIDE_KIND,
    RULE_OVERRIDE_KIND,
)
from backend.platforms.KeyMappings import normalize_shortcut_keys


VALID_MACRO_MODES = {"mouse", "keyboard", "hotkey"}
VALID_TRIGGER_HANDS = {"left", "right", "either"}
RULE_TRIGGER_TYPE_POSE = "pose"
RULE_TRIGGER_TYPE_SWIPE = "swipe"
VALID_RULE_TRIGGER_TYPES = {RULE_TRIGGER_TYPE_POSE, RULE_TRIGGER_TYPE_SWIPE}
VALID_SWIPE_DIRECTIONS = {"left", "right", "up", "down"}
VALID_TRACKED_POINTS = {value for value, _label in LANDMARK_OPTIONS}


@dataclass(frozen=True)
class MacroPointTrigger:
    hand: str
    pose_template: HandPoseTemplate
    editor_pose_template: HandPoseTemplate | None
    matcher_config: PoseMatcherConfig

    def to_dict(self) -> dict:
        payload = {
            "hand": self.hand,
            "pose_template": self.pose_template.to_dict(),
            "matcher_config": self.matcher_config.to_dict(),
        }
        if self.editor_pose_template is not None:
            payload["editor_pose_template"] = self.editor_pose_template.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "MacroPointTrigger":
        if not isinstance(data, dict):
            raise ValueError("macro point trigger must be an object")
        hand = str(data.get("hand", "right")).strip()
        if hand not in VALID_TRIGGER_HANDS:
            raise ValueError(f"invalid macro trigger hand '{hand}'")
        if not isinstance(data.get("pose_template"), dict):
            raise ValueError("macro point trigger pose_template is required")
        return cls(
            hand=hand,
            pose_template=HandPoseTemplate.from_dict(data["pose_template"]),
            editor_pose_template=(
                HandPoseTemplate.from_dict(data["editor_pose_template"])
                if isinstance(data.get("editor_pose_template"), dict)
                else None
            ),
            matcher_config=PoseMatcherConfig.from_dict(data.get("matcher_config")),
        )


@dataclass(frozen=True)
class MacroSwipeConfig:
    tracked_point: str
    direction: str
    min_displacement: float
    min_speed: float
    min_smoothness: float
    start_confirm_frames: int
    timeout_frames: int

    def to_dict(self) -> dict:
        return {
            "tracked_point": self.tracked_point,
            "direction": self.direction,
            "min_displacement": float(self.min_displacement),
            "min_speed": float(self.min_speed),
            "min_smoothness": float(self.min_smoothness),
            "start_confirm_frames": int(self.start_confirm_frames),
            "timeout_frames": int(self.timeout_frames),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MacroSwipeConfig":
        if not isinstance(data, dict):
            raise ValueError("macro swipe config must be an object")

        tracked_point = str(data.get("tracked_point", "index.tip")).strip()
        if tracked_point not in VALID_TRACKED_POINTS:
            raise ValueError(f"invalid swipe tracked_point '{tracked_point}'")

        direction = str(data.get("direction", "right")).strip()
        if direction not in VALID_SWIPE_DIRECTIONS:
            raise ValueError(f"invalid swipe direction '{direction}'")

        min_displacement = float(data.get("min_displacement", 0.18))
        min_speed = float(data.get("min_speed", 0.65))
        min_smoothness = float(data.get("min_smoothness", 0.72))
        start_confirm_frames = max(1, int(data.get("start_confirm_frames", 2)))
        timeout_frames = max(2, int(data.get("timeout_frames", 18)))

        if min_displacement <= 0.0:
            raise ValueError("swipe min_displacement must be greater than 0")
        if min_speed <= 0.0:
            raise ValueError("swipe min_speed must be greater than 0")
        if not 0.0 <= min_smoothness <= 1.0:
            raise ValueError("swipe min_smoothness must be between 0 and 1")

        return cls(
            tracked_point=tracked_point,
            direction=direction,
            min_displacement=min_displacement,
            min_speed=min_speed,
            min_smoothness=min_smoothness,
            start_confirm_frames=start_confirm_frames,
            timeout_frames=timeout_frames,
        )


@dataclass(frozen=True)
class MacroRuleTrigger:
    hand: str
    trigger_type: str
    rule_override: GestureRuleOverride | None
    start_rule_override: GestureRuleOverride | None
    swipe_config: MacroSwipeConfig | None

    @property
    def is_pose_trigger(self) -> bool:
        return self.trigger_type == RULE_TRIGGER_TYPE_POSE

    @property
    def is_swipe_trigger(self) -> bool:
        return self.trigger_type == RULE_TRIGGER_TYPE_SWIPE

    def to_dict(self) -> dict:
        payload = {
            "hand": self.hand,
            "trigger_type": self.trigger_type,
        }
        if self.rule_override is not None:
            payload["rule_override"] = self.rule_override.to_dict()
        if self.start_rule_override is not None:
            payload["start_rule_override"] = self.start_rule_override.to_dict()
        if self.swipe_config is not None:
            payload["swipe_config"] = self.swipe_config.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "MacroRuleTrigger":
        if not isinstance(data, dict):
            raise ValueError("macro rule trigger must be an object")
        hand = str(data.get("hand", "right")).strip()
        if hand not in VALID_TRIGGER_HANDS:
            raise ValueError(f"invalid macro trigger hand '{hand}'")

        trigger_type = str(data.get("trigger_type", "")).strip()
        if trigger_type not in VALID_RULE_TRIGGER_TYPES:
            if isinstance(data.get("swipe_config"), dict):
                trigger_type = RULE_TRIGGER_TYPE_SWIPE
            else:
                trigger_type = RULE_TRIGGER_TYPE_POSE

        if trigger_type == RULE_TRIGGER_TYPE_POSE:
            if not isinstance(data.get("rule_override"), dict):
                raise ValueError("macro rule trigger rule_override is required")
            return cls(
                hand=hand,
                trigger_type=trigger_type,
                rule_override=GestureRuleOverride.from_dict(data["rule_override"]),
                start_rule_override=None,
                swipe_config=None,
            )

        if not isinstance(data.get("start_rule_override"), dict):
            raise ValueError("macro swipe trigger start_rule_override is required")
        if not isinstance(data.get("swipe_config"), dict):
            raise ValueError("macro swipe trigger swipe_config is required")
        return cls(
            hand=hand,
            trigger_type=trigger_type,
            rule_override=None,
            start_rule_override=GestureRuleOverride.from_dict(data["start_rule_override"]),
            swipe_config=MacroSwipeConfig.from_dict(data["swipe_config"]),
        )


@dataclass(frozen=True)
class MacroRecord:
    id: str
    name: str
    enabled: bool
    mode: str
    trigger_kind: str
    point_trigger: MacroPointTrigger | None
    rule_trigger: MacroRuleTrigger | None
    shortcut_keys: list[str]
    created_at: str
    updated_at: str

    @property
    def is_point_trigger(self) -> bool:
        return self.trigger_kind == POINT_OVERRIDE_KIND

    @property
    def is_rule_trigger(self) -> bool:
        return self.trigger_kind == RULE_OVERRIDE_KIND

    def to_dict(self) -> dict:
        payload = {
            "id": self.id,
            "name": self.name,
            "enabled": bool(self.enabled),
            "mode": self.mode,
            "trigger_kind": self.trigger_kind,
            "shortcut_keys": list(self.shortcut_keys),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.point_trigger is not None:
            payload["point_trigger"] = self.point_trigger.to_dict()
        if self.rule_trigger is not None:
            payload["rule_trigger"] = self.rule_trigger.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict, *, target_os: str | None = None) -> "MacroRecord":
        if not isinstance(data, dict):
            raise ValueError("macro record must be an object")

        macro_id = str(data.get("id", "")).strip() or uuid4().hex
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("macro name is required")

        mode = str(data.get("mode", "mouse")).strip()
        if mode not in VALID_MACRO_MODES:
            raise ValueError(f"invalid macro mode '{mode}'")

        trigger_kind = str(data.get("trigger_kind", "")).strip()
        if trigger_kind not in {POINT_OVERRIDE_KIND, RULE_OVERRIDE_KIND}:
            trigger_kind = RULE_OVERRIDE_KIND if isinstance(data.get("rule_trigger"), dict) else POINT_OVERRIDE_KIND

        point_trigger = (
            MacroPointTrigger.from_dict(data["point_trigger"])
            if isinstance(data.get("point_trigger"), dict)
            else None
        )
        rule_trigger = (
            MacroRuleTrigger.from_dict(data["rule_trigger"])
            if isinstance(data.get("rule_trigger"), dict)
            else None
        )
        if trigger_kind == POINT_OVERRIDE_KIND and point_trigger is None:
            raise ValueError("point macro trigger payload is required")
        if trigger_kind == RULE_OVERRIDE_KIND and rule_trigger is None:
            raise ValueError("rule macro trigger payload is required")

        if "action_steps" in data:
            raise ValueError("legacy macro action_steps are no longer supported")
        raw_shortcut_keys = data.get("shortcut_keys")
        if raw_shortcut_keys is None:
            raise ValueError("macro shortcut_keys are required")
        shortcut_keys = normalize_shortcut_keys(raw_shortcut_keys, target_os=target_os)

        created_at = str(data.get("created_at", "")).strip() or datetime.now(timezone.utc).isoformat()
        updated_at = str(data.get("updated_at", "")).strip() or created_at

        return cls(
            id=macro_id,
            name=name,
            enabled=bool(data.get("enabled", True)),
            mode=mode,
            trigger_kind=trigger_kind,
            point_trigger=point_trigger,
            rule_trigger=rule_trigger,
            shortcut_keys=shortcut_keys,
            created_at=created_at,
            updated_at=updated_at,
        )

    @classmethod
    def build_new(
        cls,
        *,
        name: str,
        mode: str,
        trigger_kind: str,
        point_trigger: MacroPointTrigger | None,
        rule_trigger: MacroRuleTrigger | None,
        shortcut_keys: list[str],
        enabled: bool = True,
        macro_id: str | None = None,
        created_at: str | None = None,
        target_os: str | None = None,
    ) -> "MacroRecord":
        now = datetime.now(timezone.utc).isoformat()
        return cls.from_dict(
            {
                "id": macro_id or uuid4().hex,
                "name": name,
                "enabled": enabled,
                "mode": mode,
                "trigger_kind": trigger_kind,
                "point_trigger": point_trigger.to_dict() if point_trigger else None,
                "rule_trigger": rule_trigger.to_dict() if rule_trigger else None,
                "shortcut_keys": copy.deepcopy(shortcut_keys),
                "created_at": created_at or now,
                "updated_at": now,
            },
            target_os=target_os,
        )
