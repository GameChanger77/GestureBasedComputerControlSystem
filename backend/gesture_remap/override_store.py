from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from backend.GestureConfig import GestureConfig
from backend.gesture_remap.pose_templates import (
    HandPoseTemplate,
    PoseMatcherConfig,
    compare_pose_templates,
)
from backend.gesture_remap.rule_overrides import (
    GestureRuleOverride,
    POINT_OVERRIDE_KIND,
    RULE_OVERRIDE_KIND,
)


@dataclass(frozen=True)
class GestureOverrideRecord:
    gesture_id: str
    enabled: bool
    override_kind: str
    pose_template: HandPoseTemplate | None
    editor_pose_template: HandPoseTemplate | None
    matcher_config: PoseMatcherConfig | None
    rule_override: GestureRuleOverride | None
    updated_at: str

    def to_dict(self) -> dict:
        payload = {
            "gesture_id": self.gesture_id,
            "enabled": bool(self.enabled),
            "override_kind": self.override_kind,
            "updated_at": self.updated_at,
        }
        if self.is_point_override and self.pose_template is not None and self.matcher_config is not None:
            payload["pose_template"] = self.pose_template.to_dict()
            payload["matcher_config"] = self.matcher_config.to_dict()
            if self.editor_pose_template is not None:
                payload["editor_pose_template"] = self.editor_pose_template.to_dict()
        if self.is_rule_override and self.rule_override is not None:
            payload["rule_override"] = self.rule_override.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "GestureOverrideRecord":
        override_kind = str(data.get("override_kind", "") or "").strip()
        if override_kind not in {POINT_OVERRIDE_KIND, RULE_OVERRIDE_KIND}:
            override_kind = RULE_OVERRIDE_KIND if isinstance(data.get("rule_override"), dict) else POINT_OVERRIDE_KIND

        return cls(
            gesture_id=str(data["gesture_id"]),
            enabled=bool(data.get("enabled", True)),
            override_kind=override_kind,
            pose_template=(
                HandPoseTemplate.from_dict(data["pose_template"])
                if isinstance(data.get("pose_template"), dict)
                else None
            ),
            editor_pose_template=(
                HandPoseTemplate.from_dict(data["editor_pose_template"])
                if isinstance(data.get("editor_pose_template"), dict)
                else None
            ),
            matcher_config=(
                PoseMatcherConfig.from_dict(data.get("matcher_config"))
                if override_kind == POINT_OVERRIDE_KIND
                else None
            ),
            rule_override=(
                GestureRuleOverride.from_dict(data["rule_override"])
                if isinstance(data.get("rule_override"), dict)
                else None
            ),
            updated_at=str(data.get("updated_at", "")),
        )

    @property
    def is_point_override(self) -> bool:
        return self.override_kind == POINT_OVERRIDE_KIND

    @property
    def is_rule_override(self) -> bool:
        return self.override_kind == RULE_OVERRIDE_KIND


class GestureOverrideStore:
    VERSION = 1
    FILENAME = "gesture_overrides.json"

    def __init__(self, path: Path | str | None = None):
        self.path = self.resolve_path(path)
        self.records: Dict[str, GestureOverrideRecord] = {}
        self.load()

    @classmethod
    def resolve_path(cls, path: Path | str | None = None) -> Path:
        if path is not None:
            return Path(path).expanduser().resolve()
        config_path = GestureConfig.resolve_config_path()
        return config_path.with_name(cls.FILENAME)

    @classmethod
    def from_config(cls, config: GestureConfig | None) -> "GestureOverrideStore":
        if config is None:
            return cls()
        return cls(config.config_path.with_name(cls.FILENAME))

    def load(self):
        self.records = {}
        if not self.path.exists():
            return

        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                raise ValueError("gesture overrides must be a JSON object")
            overrides = payload.get("overrides", {})
            if not isinstance(overrides, dict):
                raise ValueError("gesture overrides payload missing 'overrides' object")
            for gesture_id, record_data in overrides.items():
                if not isinstance(record_data, dict):
                    continue
                record_payload = dict(record_data)
                record_payload.setdefault("gesture_id", gesture_id)
                record = GestureOverrideRecord.from_dict(record_payload)
                self.records[gesture_id] = record
        except Exception as exc:
            print(f"[WARN] Failed to load gesture overrides from {self.path}: {exc}")
            self.records = {}

    def save(self):
        payload = {
            "version": self.VERSION,
            "overrides": {gesture_id: record.to_dict() for gesture_id, record in sorted(self.records.items())},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=4)

    def list_records(self) -> list[GestureOverrideRecord]:
        return [self.records[key] for key in sorted(self.records)]

    def get(self, gesture_id: str) -> GestureOverrideRecord | None:
        return self.records.get(gesture_id)

    def set_override(
        self,
        gesture_id: str,
        pose_template: HandPoseTemplate,
        editor_pose_template: HandPoseTemplate | None = None,
        matcher_config: PoseMatcherConfig | None = None,
        enabled: bool = True,
    ) -> GestureOverrideRecord:
        record = GestureOverrideRecord(
            gesture_id=gesture_id,
            enabled=enabled,
            override_kind=POINT_OVERRIDE_KIND,
            pose_template=pose_template,
            editor_pose_template=editor_pose_template,
            matcher_config=matcher_config or PoseMatcherConfig(),
            rule_override=None,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.records[gesture_id] = record
        self.save()
        return record

    def set_rule_override(
        self,
        gesture_id: str,
        rule_override: GestureRuleOverride,
        enabled: bool = True,
    ) -> GestureOverrideRecord:
        record = GestureOverrideRecord(
            gesture_id=gesture_id,
            enabled=enabled,
            override_kind=RULE_OVERRIDE_KIND,
            pose_template=None,
            editor_pose_template=None,
            matcher_config=None,
            rule_override=rule_override,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.records[gesture_id] = record
        self.save()
        return record

    def editor_template_for_record(self, record: GestureOverrideRecord) -> HandPoseTemplate:
        if not record.is_point_override or record.pose_template is None:
            raise ValueError("editor pose template is only available for point overrides")
        if record.editor_pose_template is not None:
            return record.editor_pose_template
        return record.pose_template

    def reset_override(self, gesture_id: str):
        if gesture_id in self.records:
            del self.records[gesture_id]
            self.save()

    def reset_all(self):
        if self.records:
            self.records = {}
            self.save()

    def validate_override(self, registry, gesture_id: str, pose_template: HandPoseTemplate, matcher_config: PoseMatcherConfig):
        target_def = registry.get(gesture_id)
        for other_def in registry.all():
            if other_def.id == gesture_id:
                continue
            if other_def.conflict_group != target_def.conflict_group or other_def.hand != target_def.hand:
                continue
            other_record = self.get(other_def.id)
            other_template = (
                self.editor_template_for_record(other_record)
                if other_record and other_record.enabled and other_record.is_point_override
                else other_def.saved_pose_template
            )
            comparison = compare_pose_templates(other_template, pose_template, matcher_config)
            if comparison.score <= matcher_config.conflict_threshold:
                return other_def, comparison
        return None, None
