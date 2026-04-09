import json
import os
from typing import Any, Dict


class RuleLoader:
    """
    Loads and validates gesture_custom_rules.json.

    Purpose:
    - Users author custom gestures in JSON (no Python required).
    - We validate the JSON early so errors are readable and deterministic.
    - Returns a normalized dict structure for RuleCompiler to consume.
    """

    def __init__(self, path: str = "gesture_custom_rules.json"):
        self.path = path

    def load(self) -> Dict[str, Any]:
        """
        Load JSON from disk.

        Returns:
            dict: Parsed rules file (with defaults if file missing)
        """
        if not os.path.exists(self.path):
            # Missing file is not fatal; just means no custom gestures
            return {
                "version": 1,
                "global": {"default_pending_frames": 3, "default_ending_frames": 2},
                "custom_gestures": [],
            }

        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._validate(data)
        return data

    def _validate(self, data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            raise ValueError("Root must be an object")

        if data.get("version") != 1:
            raise ValueError("gesture_custom_rules.json: only version=1 supported")

        if "custom_gestures" not in data or not isinstance(data["custom_gestures"], list):
            raise ValueError("custom_gestures must be a list")

        global_cfg = data.get("global", {})
        if not isinstance(global_cfg, dict):
            raise ValueError("global must be an object")

        for i, g in enumerate(data["custom_gestures"]):
            path = f"custom_gestures[{i}]"
            if not isinstance(g, dict):
                raise ValueError(f"{path} must be an object")

            required = ["id", "name", "enabled", "mode", "type", "priority", "hand", "conditions", "action"]
            for r in required:
                if r not in g:
                    raise ValueError(f"{path}.{r} is required")

            if g["type"] not in ["pose", "hold"]:
                raise ValueError(f"{path}.type must be 'pose' or 'hold'")

            if g["mode"] not in ["mouse", "keyboard", "hotkey"]:
                raise ValueError(f"{path}.mode must be mouse|keyboard|hotkey")

            if g["hand"] not in ["left", "right", "either"]:
                raise ValueError(f"{path}.hand must be left|right|either")

            if not isinstance(g["conditions"], list):
                raise ValueError(f"{path}.conditions must be a list")

            if not isinstance(g["action"], dict) or "type" not in g["action"]:
                raise ValueError(f"{path}.action must be an object with action.type")

            if g["action"]["type"] == "macro":
                raise ValueError(
                    f"{path}.action.type='macro' is no longer supported. "
                    "Use the Macros settings page for custom shortcut gestures."
                )

            if "confirm" in g and not isinstance(g["confirm"], dict):
                raise ValueError(f"{path}.confirm must be an object if present")

        if "custom_macros" in data:
            raise ValueError(
                "custom_macros is no longer supported in gesture_custom_rules.json. "
                "Use the Macros settings page for custom shortcut gestures."
            )
