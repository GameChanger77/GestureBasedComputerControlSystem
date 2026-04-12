from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.GestureConfig import GestureConfig
from backend.gesture_remap.pose_templates import (
    HandPoseTemplate,
    PoseMatcherConfig,
    compare_pose_templates,
)
from backend.gesture_remap.rule_overrides import RULE_OVERRIDE_KIND, GestureRuleOverride
from backend.macros.macro_models import (
    DOMINANT_TRIGGER_HAND,
    MacroRecord,
    MacroRuleTrigger,
    RULE_TRIGGER_TYPE_POSE,
)
from backend.platforms.KeyboardBackendFactory import normalize_os_name


class MacroStore:
    VERSION = 2
    FILENAME = "gesture_macros.json"
    _STARTER_MACRO_SPECS = (
        ("starter_hotkey_copy", "Copy", "middle.tip", "c"),
        ("starter_hotkey_paste", "Paste", "ring.tip", "v"),
        ("starter_hotkey_undo", "Undo", "pinky.tip", "z"),
    )

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        target_os: str | None = None,
        seed_defaults: bool = False,
    ):
        self.path = self.resolve_path(path)
        self.target_os = normalize_os_name(target_os)
        self.seed_defaults = bool(seed_defaults)
        self.records: dict[str, MacroRecord] = {}
        self.load()

    @classmethod
    def resolve_path(cls, path: Path | str | None = None) -> Path:
        if path is not None:
            return Path(path).expanduser().resolve()
        config_path = GestureConfig.resolve_config_path()
        return config_path.with_name(cls.FILENAME)

    @classmethod
    def from_config(
        cls,
        config: GestureConfig | None,
        *,
        target_os: str | None = None,
        seed_defaults: bool = True,
    ) -> "MacroStore":
        if config is None:
            return cls(target_os=target_os, seed_defaults=seed_defaults)
        return cls(
            config.config_path.with_name(cls.FILENAME),
            target_os=target_os,
            seed_defaults=seed_defaults,
        )

    def load(self):
        self.records = {}
        if not self.path.exists():
            if self.seed_defaults:
                self.records = self._build_starter_macros()
                self.save()
            return
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            records = payload.get("macros", {})
            if not isinstance(records, dict):
                raise ValueError("macro store payload missing 'macros' object")
            for macro_id, record_data in records.items():
                if not isinstance(record_data, dict):
                    continue
                record_payload = dict(record_data)
                record_payload.setdefault("id", macro_id)
                try:
                    record = MacroRecord.from_dict(record_payload, target_os=self.target_os)
                except Exception as exc:
                    print(f"[WARN] Skipped macro '{macro_id}' from {self.path}: {exc}")
                    continue
                self.records[record.id] = record
        except Exception as exc:
            print(f"[WARN] Failed to load gesture macros from {self.path}: {exc}")
            self.records = {}

    def _default_shortcut_keys(self, key_name: str) -> list[str]:
        modifier = "left_cmd" if self.target_os == "Darwin" else "left_ctrl"
        return [modifier, str(key_name).strip().lower()]

    def _build_starter_macros(self) -> dict[str, MacroRecord]:
        created_at = datetime.now(timezone.utc).isoformat()
        records: dict[str, MacroRecord] = {}
        for macro_id, name, pinch_target, key_name in self._STARTER_MACRO_SPECS:
            records[macro_id] = MacroRecord.build_new(
                name=name,
                mode="hotkey",
                trigger_kind=RULE_OVERRIDE_KIND,
                point_trigger=None,
                rule_trigger=MacroRuleTrigger(
                    hand=DOMINANT_TRIGGER_HAND,
                    trigger_type=RULE_TRIGGER_TYPE_POSE,
                    rule_override=GestureRuleOverride(
                        conditions=[
                            {
                                "op": "pinch_distance_lt",
                                "a": "thumb.tip",
                                "b": pinch_target,
                                "value": 0.3,
                                "space": "wrist",
                            }
                        ],
                        pending_frames=3,
                        ending_frames=2,
                    ),
                    start_rule_override=None,
                    swipe_config=None,
                ),
                shortcut_keys=self._default_shortcut_keys(key_name),
                macro_id=macro_id,
                created_at=created_at,
                target_os=self.target_os,
            )
        return records

    def save(self):
        payload = {
            "version": self.VERSION,
            "macros": {macro_id: record.to_dict() for macro_id, record in sorted(self.records.items())},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=4)

    def list_records(self) -> list[MacroRecord]:
        return [self.records[key] for key in sorted(self.records)]

    def get(self, macro_id: str) -> MacroRecord | None:
        return self.records.get(macro_id)

    def upsert(self, record: MacroRecord) -> MacroRecord:
        self.records[record.id] = record
        self.save()
        return record

    def delete(self, macro_id: str):
        if macro_id in self.records:
            del self.records[macro_id]
            self.save()

    @staticmethod
    def _built_in_active_in_mode(definition, mode: str) -> bool:
        if definition.section == "mouse":
            return mode == "mouse"
        if definition.id == "switch_to_keyboard":
            return mode in {"mouse", "hotkey"}
        if definition.id == "switch_to_hotkey":
            return mode in {"mouse", "keyboard"}
        if definition.id == "switch_to_mouse":
            return mode in {"keyboard", "hotkey"}
        return False

    def validate_point_trigger(
        self,
        registry,
        *,
        macro_id: str | None,
        mode: str,
        pose_template: HandPoseTemplate,
        matcher_config: PoseMatcherConfig,
    ):
        for definition in registry.all():
            if not self._built_in_active_in_mode(definition, mode):
                continue
            comparison = compare_pose_templates(
                definition.saved_pose_template,
                pose_template,
                matcher_config,
            )
            if comparison.score <= matcher_config.conflict_threshold:
                return definition, comparison

        for record in self.list_records():
            if record.id == macro_id or not record.enabled or not record.is_point_trigger:
                continue
            if record.mode != mode:
                continue
            other_trigger = record.point_trigger
            if other_trigger is None:
                continue
            other_template = other_trigger.editor_pose_template or other_trigger.pose_template
            comparison = compare_pose_templates(other_template, pose_template, matcher_config)
            if comparison.score <= matcher_config.conflict_threshold:
                return record, comparison
        return None, None
