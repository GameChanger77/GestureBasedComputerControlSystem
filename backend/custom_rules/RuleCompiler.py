from __future__ import annotations

from typing import Any, Dict

from backend.custom_rules.ConditionEvaluator import ConditionEvaluator
from backend.custom_rules.RuleGestures import RuleSnapshotGesture, RuleContinuousGesture
from backend.custom_rules.MacroChainRecognizer import MacroChainRecognizer


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

    def compile_macro(
            self,
            action,
            macro_rule: Dict[str, Any],
            gesture_rule_by_id: Dict[str, Any],
            global_cfg: Dict[str, Any],
    ):
        """
        Compile a macro rule into a MacroChainRecognizer.

        Key behavior:
        - Each step compiles into a SILENT recognizer (execute_action is replaced with no-op)
          so steps do not trigger their own actions during macro evaluation.
        """
        default_step_timeout = int(global_cfg.get("macro_step_timeout_ms", 900))
        cooldown_ms = int(macro_rule.get("cooldown_ms", global_cfg.get("macro_cooldown_ms", 800)))

        steps_compiled = []
        for step in macro_rule["steps"]:
            gid = step["gesture_id"]
            if gid not in gesture_rule_by_id:
                raise ValueError(f"Macro step references unknown gesture_id: {gid}")

            # Compile the primitive rule into a recognizer
            rec = self.compile_gesture(action, gesture_rule_by_id[gid], global_cfg)

            # Make step recognizer "silent" (do not execute its own action)
            rec.execute_action = lambda data: None

            steps_compiled.append({
                "gesture_id": gid,
                "recognizer": rec,
                "max_delay_ms": int(step.get("max_delay_ms", default_step_timeout)),
            })

        return MacroChainRecognizer(
            action=action,
            priority=int(macro_rule["priority"]),
            steps=steps_compiled,
            macro_action=macro_rule["action"],
            config=self.config,
            screen_width=self.screen_width,
            screen_height=self.screen_height,
            cooldown_ms=cooldown_ms,
            sequence_rules=macro_rule.get("sequence_rules", {}),
            name=macro_rule.get("name", macro_rule.get("id", "Macro")),
        )