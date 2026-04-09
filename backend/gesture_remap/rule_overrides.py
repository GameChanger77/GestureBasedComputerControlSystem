from __future__ import annotations

import copy
from dataclasses import dataclass

from backend.custom_rules.condition_catalog import CONDITION_DEFINITIONS


RULE_OVERRIDE_KIND = "rule"
POINT_OVERRIDE_KIND = "point"


@dataclass(frozen=True)
class GestureRuleOverride:
    conditions: list[dict]
    pending_frames: int
    ending_frames: int

    def to_dict(self) -> dict:
        return {
            "conditions": copy.deepcopy(self.conditions),
            "confirm": {
                "pending_frames": int(self.pending_frames),
                "ending_frames": int(self.ending_frames),
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GestureRuleOverride":
        if not isinstance(data, dict):
            raise ValueError("rule override must be an object")

        conditions = data.get("conditions", [])
        if not isinstance(conditions, list):
            raise ValueError("rule override conditions must be a list")

        confirm = data.get("confirm", {})
        if confirm is None:
            confirm = {}
        if not isinstance(confirm, dict):
            raise ValueError("rule override confirm must be an object")

        normalized_conditions = [cls._normalize_condition(condition) for condition in conditions]
        return cls(
            conditions=normalized_conditions,
            pending_frames=int(confirm.get("pending_frames", 1)),
            ending_frames=int(confirm.get("ending_frames", 1)),
        )

    @staticmethod
    def _normalize_condition(condition: dict) -> dict:
        if not isinstance(condition, dict):
            raise ValueError("rule condition must be an object")

        op = str(condition.get("op", "")).strip()
        if op == "only_fingers_extended.json":
            op = "only_fingers_extended"
        if op not in CONDITION_DEFINITIONS:
            raise ValueError(f"unsupported rule condition op '{op}'")

        normalized = {"op": op}
        for field in CONDITION_DEFINITIONS[op]["fields"]:
            name = field["name"]
            default_value = copy.deepcopy(field.get("default"))
            raw_value = condition.get(name, default_value)
            normalized[name] = GestureRuleOverride._coerce_field_value(field, raw_value)
        return normalized

    @staticmethod
    def _coerce_field_value(field: dict, value):
        field_type = field["type"]
        if field_type == "bool":
            return bool(value)
        if field_type == "int":
            return int(value)
        if field_type == "float":
            return float(value)
        if field_type == "enum":
            valid_values = {option[0] for option in field.get("options", [])}
            normalized_value = str(value)
            if normalized_value not in valid_values:
                raise ValueError(f"invalid value '{normalized_value}' for {field['name']}")
            return normalized_value
        if field_type == "multi_enum":
            if not isinstance(value, (list, tuple)):
                raise ValueError(f"{field['name']} must be a list")
            valid_values = {option[0] for option in field.get("options", [])}
            normalized_values = [str(item) for item in value if str(item) in valid_values]
            if not normalized_values:
                raise ValueError(f"{field['name']} must include at least one value")
            return normalized_values
        raise ValueError(f"unsupported field type '{field_type}'")
