from __future__ import annotations

import json
from pathlib import Path

from backend.GestureConfig import GestureConfig
from backend.gesture_remap.pose_templates import (
    HandPoseTemplate,
    PoseMatcherConfig,
    compare_pose_templates,
)
from backend.macros.macro_models import MacroRecord
from backend.platforms.KeyboardBackendFactory import normalize_os_name


class MacroStore:
    VERSION = 2
    FILENAME = "gesture_macros.json"

    def __init__(self, path: Path | str | None = None, *, target_os: str | None = None):
        self.path = self.resolve_path(path)
        self.target_os = normalize_os_name(target_os)
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
    ) -> "MacroStore":
        if config is None:
            return cls(target_os=target_os)
        return cls(config.config_path.with_name(cls.FILENAME), target_os=target_os)

    def load(self):
        self.records = {}
        if not self.path.exists():
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
    def _hands_overlap(candidate_hand: str, other_hand: str) -> bool:
        candidate_set = {"left", "right"} if candidate_hand == "either" else {candidate_hand}
        other_set = {"left", "right"} if other_hand == "either" else {other_hand}
        return bool(candidate_set & other_set)

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
        hand: str,
        pose_template: HandPoseTemplate,
        matcher_config: PoseMatcherConfig,
    ):
        for definition in registry.all():
            if not self._built_in_active_in_mode(definition, mode):
                continue
            if not self._hands_overlap(hand, definition.hand):
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
            if other_trigger is None or not self._hands_overlap(hand, other_trigger.hand):
                continue
            other_template = other_trigger.editor_pose_template or other_trigger.pose_template
            comparison = compare_pose_templates(other_template, pose_template, matcher_config)
            if comparison.score <= matcher_config.conflict_threshold:
                return record, comparison
        return None, None
