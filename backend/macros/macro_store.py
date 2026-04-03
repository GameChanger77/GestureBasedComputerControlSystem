from __future__ import annotations

import json
from pathlib import Path

from backend.GestureConfig import GestureConfig
from backend.macros.macro_models import MacroRecord


class MacroStore:
    VERSION = 1
    FILENAME = "gesture_macros.json"

    def __init__(self, path: Path | str | None = None):
        self.path = self.resolve_path(path)
        self.records: dict[str, MacroRecord] = {}
        self.load()

    @classmethod
    def resolve_path(cls, path: Path | str | None = None) -> Path:
        if path is not None:
            return Path(path).expanduser().resolve()
        config_path = GestureConfig.resolve_config_path()
        return config_path.with_name(cls.FILENAME)

    @classmethod
    def from_config(cls, config: GestureConfig | None) -> "MacroStore":
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
            records = payload.get("macros", {})
            if not isinstance(records, dict):
                raise ValueError("macro store payload missing 'macros' object")
            for macro_id, record_data in records.items():
                if not isinstance(record_data, dict):
                    continue
                record_payload = dict(record_data)
                record_payload.setdefault("id", macro_id)
                record = MacroRecord.from_dict(record_payload)
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
