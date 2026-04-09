from __future__ import annotations

from backend.macros.macro_recognizers import (
    PointMacroTriggerRecognizer,
    RuleMacroTriggerRecognizer,
    SwipeMacroTriggerRecognizer,
)


class RuleCompiler:
    """Compiles saved macro records into concrete gesture recognizers."""

    def __init__(self, config, screen_width: int, screen_height: int):
        """
        Args:
            config: GestureConfig (used for thresholds and runtime settings)
            screen_width/screen_height: Needed to map camera coordinates to screen pixels
        """
        self.config = config
        self.screen_width = screen_width
        self.screen_height = screen_height

    def compile_ui_macro(self, action, macro_record):
        if macro_record.is_rule_trigger and macro_record.rule_trigger.is_swipe_trigger:
            return SwipeMacroTriggerRecognizer(
                action,
                name=macro_record.name,
                trigger=macro_record.rule_trigger,
                shortcut_keys=macro_record.shortcut_keys,
            )

        if macro_record.is_rule_trigger:
            return RuleMacroTriggerRecognizer(
                action,
                name=macro_record.name,
                trigger=macro_record.rule_trigger,
                shortcut_keys=macro_record.shortcut_keys,
            )

        return PointMacroTriggerRecognizer(
            action,
            name=macro_record.name,
            trigger=macro_record.point_trigger,
            shortcut_keys=macro_record.shortcut_keys,
            pending_frames=int(self.config.get("click_pending_frames", 3)),
            ending_frames=int(self.config.get("ending_frames", 2)),
        )
