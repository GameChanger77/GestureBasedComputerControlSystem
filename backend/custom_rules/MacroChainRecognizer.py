import time
from typing import Any, Dict, List, Optional

from backend.HandsData import HandsData
from backend.gestures.GestureRecognizer import GestureRecognizer
from backend.gestures.GestureStateMachine import GestureState
from backend.gestures.GestureUtils import camera_to_screen


class MacroChainRecognizer(GestureRecognizer):
    """
    Executes an ordered gesture sequence (macro).

    What it does:
    - Watches for step[0] gesture to be confirmed
    - Then watches for step[1] within max_delay_ms
    - ... continues until final step is confirmed
    - Executes ONE final macro action (click/move/scroll/etc.)
    - Applies cooldown so it does not immediately retrigger

    Key design choice:
    - Each step uses a "silent" recognizer (its execute_action() is no-op)
      so step gestures do NOT fire their own actions while being used in a macro.
    """

    def __init__(
        self,
        action,
        priority: int,
        steps: List[Dict[str, Any]],
        macro_action: Dict[str, Any],
        config,
        screen_width: int,
        screen_height: int,
        cooldown_ms: int = 800,
        sequence_rules: Optional[Dict[str, Any]] = None,
        name: str = "MacroChain",
    ):
        super().__init__(action, priority)
        self.name = name

        # Steps: list of dicts:
        #   { "gesture_id": str, "recognizer": GestureRecognizer, "max_delay_ms": int }
        self.steps = steps
        self.macro_action = macro_action

        self.config = config
        self.screen_width = screen_width
        self.screen_height = screen_height

        self.cooldown_ms = int(cooldown_ms)
        self.sequence_rules = sequence_rules or {}

        # If true, Strategizer can suppress other lower-priority recognizers
        # while this macro is "in progress".
        self.consumes_events = bool(self.sequence_rules.get("consumes_events", True))

        # Optional: allow some frames with no hands detected without resetting
        self.allow_intermediate_idle_frames = int(self.sequence_rules.get("allow_intermediate_idle_frames", 10))

        self.strict_order = bool(self.sequence_rules.get("strict_order", True))
        self.reset_on_wrong_gesture = bool(self.sequence_rules.get("reset_on_wrong_gesture", True))

        # Runtime state
        self._step_index = 0
        self._last_step_time = None  # time.monotonic() timestamp when last step completed
        self._cooldown_until = 0.0
        self._idle_frames = 0

        self._state = GestureState.IDLE

    # ------------------------------------------------------------
    # GestureRecognizer required interface
    # ------------------------------------------------------------

    def detect_gesture(self, hands_data: HandsData):
        """
        Not used for macros.

        Macro recognition uses update() to evaluate a multi-step sequence.
        """
        return False, None

    def execute_action(self, data):
        """
        Not used directly (macro action executes internally).
        """
        pass

    def update(self, hands_data: HandsData, frame_capture_ts_ns=None) -> bool:
        """
        Update macro sequence state.

        Returns:
            bool: True if the macro action was executed this frame.
        """
        now = time.monotonic()

        # Cooldown gate
        if now < self._cooldown_until:
            self._state = GestureState.IDLE
            return False

        # Optional idle-frames allowance
        if not hands_data.wrist.has_left and not hands_data.wrist.has_right:
            self._idle_frames += 1
            if self._idle_frames > self.allow_intermediate_idle_frames:
                self.reset()
            return False
        else:
            self._idle_frames = 0

        # If we're mid-chain, enforce per-step timeout
        if self._step_index > 0 and self._last_step_time is not None:
            max_delay_ms = int(self.steps[self._step_index].get("max_delay_ms", 900))
            if (now - self._last_step_time) * 1000.0 > max_delay_ms:
                self._debug(f"Timeout waiting for step {self._step_index + 1}. Resetting.")
                self.reset()
                return False

        # Optional: wrong-gesture reset (basic version)
        if self.reset_on_wrong_gesture and self._step_index > 0:
            # If ANY non-current step gesture is currently detected (raw),
            # reset to avoid false sequences.
            expected_idx = self._step_index
            for i, st in enumerate(self.steps):
                if i == expected_idx:
                    continue
                # Don't consider already completed steps as "wrong"
                if i < expected_idx:
                    continue

                other_rec = st["recognizer"]
                detected, _ = other_rec.detect_gesture(hands_data)
                if detected:
                    self._debug(f"Wrong gesture detected ({st['gesture_id']}) while expecting {self.steps[expected_idx]['gesture_id']}. Resetting.")
                    self.reset()
                    return False

        # Evaluate current expected step
        expected = self.steps[self._step_index]
        rec = expected["recognizer"]

        # Rising-edge detection: step is satisfied when recognizer transitions into ACTIVE
        was_active = rec.is_active
        rec.update(hands_data)  # silent recognizer: does NOT execute step actions
        now_active = rec.is_active

        if (not was_active) and now_active:
            # Step satisfied
            self._debug(f"Step {self._step_index + 1}/{len(self.steps)} satisfied: {expected['gesture_id']}")
            self._step_index += 1
            self._last_step_time = now

            # If finished, execute macro action once
            if self._step_index >= len(self.steps):
                self._debug("Macro complete! Executing macro action.")
                self._execute_macro_action(hands_data)
                self._cooldown_until = now + (self.cooldown_ms / 1000.0)
                self.reset()  # reset sequence state after firing
                return True

            # Reset the next step recognizer so it starts clean
            self.steps[self._step_index]["recognizer"].reset()

        # Macro is considered "active" if it has started (step_index > 0)
        self._state = GestureState.ACTIVE if self._step_index > 0 else GestureState.IDLE
        return False

    def reset(self):
        """Reset the macro chain back to step 0."""
        self._step_index = 0
        self._last_step_time = None
        self._idle_frames = 0
        self._state = GestureState.IDLE

        # Reset all step recognizers so state machines don't carry across attempts
        for st in self.steps:
            st["recognizer"].reset()

    @property
    def is_active(self):
        """True if macro is currently in progress (between step 1 and final)."""
        return self._state == GestureState.ACTIVE

    @property
    def current_state(self):
        """Expose state for debugging panels."""
        return self._state

    # ------------------------------------------------------------
    # Macro action execution
    # ------------------------------------------------------------

    def _execute_macro_action(self, hands_data: HandsData):
        """
        Execute the final macro action.

        Supported (today, with your Action.py):
        - left_click / right_click (requires screen coords)
        - mouse_move (requires screen coords)
        - scroll (dx, dy)
        """
        action_spec = self.macro_action
        a_type = action_spec.get("type")
        params = action_spec.get("params", {})

        safe_margin = int(self.config.get("screen_safe_margin", 50))

        if a_type in ("left_click", "right_click", "mouse_move"):
            at = params.get("at", "index.tip")
            space = params.get("space", "camera")
            if space != "camera":
                self._debug("Macro mouse actions require space='camera'. Skipping action.")
                return

            # Choose whichever hand exists (prefer right)
            hand_camera = None
            if hands_data.camera.has_right:
                hand_camera = hands_data.camera.right
            elif hands_data.camera.has_left:
                hand_camera = hands_data.camera.left
            else:
                return

            finger_name, which = at.split(".")
            finger = getattr(hand_camera, finger_name, None)
            if finger is None:
                return

            pt = getattr(finger, which, None)
            if pt is None:
                return

            x, y = camera_to_screen(pt, self.screen_width, self.screen_height, safe_margin=safe_margin)

            if a_type == "left_click":
                self.action.left_click(x, y)
            elif a_type == "right_click":
                self.action.right_click(x, y)
            else:
                self.action.move_cursor(x, y)

            return

        if a_type == "scroll":
            dx = int(params.get("delta_x", 0))
            dy = int(params.get("delta_y", 0))
            self.action.scroll(delta_x=dx, delta_y=dy)
            return

        self._debug(f"Unsupported macro action type: {a_type}")

    def _debug(self, msg: str):
        if bool(self.config.get("debug_mode", False)):
            print(f"[Macro:{self.name}] {msg}")
