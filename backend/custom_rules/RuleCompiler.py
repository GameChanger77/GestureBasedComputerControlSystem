from __future__ import annotations

from typing import Any, Dict

from backend.custom_rules.ConditionEvaluator import ConditionEvaluator
from backend.custom_rules.RuleGestures import RuleSnapshotGesture, RuleContinuousGesture


class RuleCompiler:
    def __init__(self, config, screen_width: int, screen_height: int):
        self.config = config
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.evaluator = ConditionEvaluator()

    def compile_gesture(self, action, rule: Dict[str, Any], global_cfg: Dict[str, Any]):
        confirm = rule.get("confirm", {})
        pending = int(confirm.get("pending_frames", global_cfg.get("default_pending_frames", 3)))
        ending = int(confirm.get("ending_frames", global_cfg.get("default_ending_frames", 2)))

        gtype = rule["type"]
        if gtype == "pose":
            return RuleSnapshotGesture(
                action, self.screen_width, self.screen_height,
                self.config, self.evaluator, rule, pending, ending
            )
        else:
            return RuleContinuousGesture(
                action, self.screen_width, self.screen_height,
                self.config, self.evaluator, rule, pending, ending
            )