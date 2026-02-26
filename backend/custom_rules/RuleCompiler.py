from __future__ import annotations

from typing import Any, Dict

from backend.custom_rules.ConditionEvaluator import ConditionEvaluator
from backend.custom_rules.RuleGestures import RuleSnapshotGesture, RuleContinuousGesture


class RuleCompiler:
    """
    Compiles JSON gesture rules into concrete GestureRecognizer objects.

    Why this exists:
    - JSON describes a gesture at a high level (conditions + action).
    - The Strategizer expects real GestureRecognizer instances.
    - This bridges the gap.

    Mapping:
    - type == "pose" -> SnapshotGestureRecognizer (fires once per activation)
    - type == "hold" -> ContinuousGestureRecognizer (fires every frame while held)
    """

    def __init__(self, config, screen_width: int, screen_height: int):
        """
        Args:
            config: GestureConfig (used for screen_safe_margin, thresholds, etc.)
            screen_width/screen_height: Needed to map camera coordinates to screen pixels
        """
        self.config = config
        self.screen_width = screen_width
        self.screen_height = screen_height

        # ConditionEvaluator is shared across all compiled gestures
        self.evaluator = ConditionEvaluator()

    def compile_gesture(self, action, rule: Dict[str, Any], global_cfg: Dict[str, Any]):
        """
        Compile a single JSON rule into a recognizer instance.

        Args:
            action: Action instance (OS controls)
            rule: One gesture rule from custom_gestures[]
            global_cfg: global config block (default debounce frames)

        Returns:
            GestureRecognizer: RuleSnapshotGesture or RuleContinuousGesture
        """
        # Debounce configuration: confirm is optional; fall back to global defaults
        confirm = rule.get("confirm", {})
        pending = int(confirm.get("pending_frames", global_cfg.get("default_pending_frames", 3)))
        ending = int(confirm.get("ending_frames", global_cfg.get("default_ending_frames", 2)))

        # Pick recognizer type based on rule["type"]
        gtype = rule["type"]
        if gtype == "pose":
            return RuleSnapshotGesture(
                action,
                self.screen_width,
                self.screen_height,
                self.config,
                self.evaluator,
                rule,
                pending,
                ending,
            )
        else:
            return RuleContinuousGesture(
                action,
                self.screen_width,
                self.screen_height,
                self.config,
                self.evaluator,
                rule,
                pending,
                ending,
            )