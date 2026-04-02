from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from backend.gesture_remap.pose_templates import HandPoseTemplate, PoseMatcherConfig
from backend.gesture_remap.rule_overrides import (
    GestureRuleOverride,
    POINT_OVERRIDE_KIND,
    RULE_OVERRIDE_KIND,
)
from backend.gestures.keyboard_mode.KeyCodes import normalize_key
from backend.macros.macro_step_catalog import STEP_DEFINITIONS


VALID_MACRO_MODES = {"mouse", "keyboard", "hotkey"}
VALID_TRIGGER_HANDS = {"left", "right", "either"}


@dataclass(frozen=True)
class MacroActionStep:
    step_type: str
    params: dict

    def to_dict(self) -> dict:
        return {
            "type": self.step_type,
            "params": copy.deepcopy(self.params),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MacroActionStep":
        if not isinstance(data, dict):
            raise ValueError("macro step must be an object")

        step_type = str(data.get("type", "")).strip()
        if step_type not in STEP_DEFINITIONS:
            raise ValueError(f"unsupported macro step type '{step_type}'")

        params = data.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ValueError("macro step params must be an object")

        normalized_params = {}
        for field in STEP_DEFINITIONS[step_type]["fields"]:
            name = field["name"]
            raw_value = params.get(name, copy.deepcopy(field.get("default")))
            normalized_params[name] = cls._coerce_field_value(field, raw_value)
        return cls(step_type=step_type, params=normalized_params)

    @staticmethod
    def _coerce_field_value(field: dict, value):
        field_type = field["type"]
        if field_type == "int":
            return int(value)
        if field_type == "float":
            return float(value)
        if field_type == "key":
            normalized = normalize_key(value)
            if not normalized:
                raise ValueError(f"{field['name']} must be a valid key")
            return normalized
        if field_type == "key_list":
            if isinstance(value, str):
                raw_items = [item.strip() for item in value.split(",")]
            elif isinstance(value, (list, tuple)):
                raw_items = [str(item).strip() for item in value]
            else:
                raise ValueError(f"{field['name']} must be a list of keys")
            normalized_items = [normalize_key(item) for item in raw_items if normalize_key(item)]
            if not normalized_items:
                raise ValueError(f"{field['name']} must contain at least one key")
            return normalized_items
        raise ValueError(f"unsupported macro step field type '{field_type}'")


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
class MacroRuleTrigger:
    hand: str
    rule_override: GestureRuleOverride

    def to_dict(self) -> dict:
        return {
            "hand": self.hand,
            "rule_override": self.rule_override.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MacroRuleTrigger":
        if not isinstance(data, dict):
            raise ValueError("macro rule trigger must be an object")
        hand = str(data.get("hand", "right")).strip()
        if hand not in VALID_TRIGGER_HANDS:
            raise ValueError(f"invalid macro trigger hand '{hand}'")
        if not isinstance(data.get("rule_override"), dict):
            raise ValueError("macro rule trigger rule_override is required")
        return cls(
            hand=hand,
            rule_override=GestureRuleOverride.from_dict(data["rule_override"]),
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
    action_steps: list[MacroActionStep]
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
            "action_steps": [step.to_dict() for step in self.action_steps],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.point_trigger is not None:
            payload["point_trigger"] = self.point_trigger.to_dict()
        if self.rule_trigger is not None:
            payload["rule_trigger"] = self.rule_trigger.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "MacroRecord":
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

        action_steps_raw = data.get("action_steps", [])
        if not isinstance(action_steps_raw, list) or not action_steps_raw:
            raise ValueError("macro action_steps must be a non-empty list")
        action_steps = [MacroActionStep.from_dict(item) for item in action_steps_raw]

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
            action_steps=action_steps,
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
        action_steps: list[MacroActionStep],
        enabled: bool = True,
        macro_id: str | None = None,
        created_at: str | None = None,
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
                "action_steps": [step.to_dict() for step in action_steps],
                "created_at": created_at or now,
                "updated_at": now,
            }
        )
