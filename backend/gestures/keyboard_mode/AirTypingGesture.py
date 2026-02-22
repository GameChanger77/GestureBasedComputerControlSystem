import math
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from backend.HandsData import HandsData
from backend.gestures.GestureRecognizer import GestureRecognizer
from backend.gestures.GestureUtils import get_finger_angle
from backend.keyboard.KeyCodes import LOCK_KEYS, MODIFIER_KEYS, REPEATABLE_KEYS


class FingerPhase(Enum):
    HOVER = "hover"
    PRESSED = "pressed"


class FingerPhaseV2(Enum):
    MISSING = "missing"
    TRACKING = "tracking"
    ARMED = "armed"
    PRESSED = "pressed"
    RELEASE_WAIT = "release_wait"


@dataclass
class FingerRuntime:
    phase: FingerPhase = FingerPhase.HOVER
    active_slot_id: Optional[str] = None
    active_action_key: Optional[str] = None
    last_press_ts: float = 0.0
    last_repeat_ts: float = 0.0
    press_confidence: float = 0.0
    hover_slot_id: Optional[str] = None
    hover_frames: int = 0
    hover_baseline_bend: Optional[float] = None
    hover_baseline_radius: Optional[float] = None
    hover_baseline_z: Optional[float] = None
    last_bend: Optional[float] = None
    last_radius: Optional[float] = None
    last_z: Optional[float] = None
    last_ts: Optional[float] = None


@dataclass
class FingerProfileV2:
    calibrated: bool = False
    neutral_tip: Optional[Tuple[float, float, float]] = None
    forward_sigma: float = 0.0
    lateral_sigma: float = 0.0
    velocity_sigma: float = 0.0
    forward_polarity: float = 1.0
    forward_polarity_locked: bool = False
    samples: deque = field(default_factory=lambda: deque(maxlen=240))


@dataclass
class FingerRuntimeV2:
    phase: FingerPhaseV2 = FingerPhaseV2.MISSING
    hover_slot_id: Optional[str] = None
    lock_slot_id: Optional[str] = None
    lock_action_key: Optional[str] = None
    lock_frames: int = 0
    active_slot_id: Optional[str] = None
    active_action_key: Optional[str] = None
    modifier_held: bool = False
    last_press_ts: float = 0.0
    last_repeat_ts: float = 0.0
    last_forward: float = 0.0
    last_velocity: float = 0.0
    last_ts: Optional[float] = None
    rearm_frames: int = 0
    press_confidence: float = 0.0
    forward_disp: float = 0.0
    lateral_disp: float = 0.0
    normalized_forward: float = 0.0
    baseline_z: Optional[float] = None
    baseline_tip: Optional[Tuple[float, float, float]] = None
    last_tip: Optional[Tuple[float, float, float]] = None
    lateral_velocity: float = 0.0
    camera_forward_disp: float = 0.0
    camera_forward_velocity: float = 0.0
    forward_velocity_samples: deque = field(default_factory=deque)
    lateral_velocity_samples: deque = field(default_factory=deque)
    camera_forward_velocity_samples: deque = field(default_factory=deque)


@dataclass
class HandFrame:
    left: float
    top: float
    width: float
    height: float


class AirTypingGesture(GestureRecognizer):
    """
    Fingertip-anchored in-air typing recognizer.

    Each hand owns half the keyboard and that half follows the hand in real time.
    Presses are detected from finger bend and fingertip radius change relative to the wrist.
    """

    _legacy_v2_warning_emitted = False
    _simple_velocity_only_warning_emitted = False

    def __init__(self, action, config, priority=15):
        super().__init__(action, priority=priority)
        self.config = config

        self.require_both_hands = bool(self.config.get("keyboard_require_both_hands", True))
        self.pause_on_hand_loss = bool(self.config.get("keyboard_pause_on_hand_loss", True))
        self.resume_stability_frames = int(self.config.get("keyboard_resume_stability_frames", 4))
        self.use_thumb_fingers = bool(self.config.get("keyboard_use_thumb_fingers", True))
        self.active_fingers = self.config.get("keyboard_active_fingers", ["index"])
        if not isinstance(self.active_fingers, list) or not self.active_fingers:
            self.active_fingers = ["index"]

        self.assign_hands_by_x = bool(self.config.get("keyboard_assign_hands_by_x", True))
        self.keyboard_split_layout = bool(self.config.get("keyboard_split_layout", False))
        self.single_hand_center_deadband = float(self.config.get("keyboard_single_hand_center_deadband", 0.08))
        self.flip_x_for_mapping = bool(
            self.config.get(
                "keyboard_flip_x_for_mapping",
                self.config.get("preview_flip_horizontal", True),
            )
        )

        # Timing / debounce
        self.press_hover_frames = int(self.config.get("keyboard_press_hover_frames", 2))
        self.min_refractory_ms = int(self.config.get("keyboard_min_key_refractory_ms", 130))
        self.min_global_key_interval_ms = int(self.config.get("keyboard_min_global_key_interval_ms", 35))
        self.repeat_delay_ms = int(self.config.get("keyboard_repeat_delay_ms", 450))
        self.repeat_rate_hz = int(self.config.get("keyboard_repeat_rate_hz", 8))

        # Wrist-relative press model
        self.hover_baseline_alpha = float(self.config.get("keyboard_hover_baseline_alpha", 0.15))
        self.press_bend_threshold = float(self.config.get("keyboard_press_bend_threshold_deg", 38.0))
        self.press_bend_delta_threshold = float(self.config.get("keyboard_press_bend_delta_deg", 12.0))
        self.press_radius_drop_threshold = float(self.config.get("keyboard_press_radius_drop", 0.05))
        self.release_bend_threshold = float(self.config.get("keyboard_release_bend_threshold_deg", 18.0))
        self.release_radius_drop_threshold = float(self.config.get("keyboard_release_radius_drop", 0.018))
        self.press_depth_threshold = float(self.config.get("keyboard_press_depth_threshold", 0.010))
        self.press_depth_velocity_threshold = float(self.config.get("keyboard_press_depth_velocity_threshold", 0.02))
        self.release_depth_threshold = float(self.config.get("keyboard_release_depth_threshold", 0.004))

        # Hand-following split-keyboard geometry
        self.wrist_ema_alpha = float(self.config.get("keyboard_wrist_ema_alpha", 0.28))
        self.half_width_scale = float(self.config.get("keyboard_hand_half_width_scale", 3.2))
        self.half_width_min = float(self.config.get("keyboard_hand_half_width_min", 0.22))
        self.half_width_max = float(self.config.get("keyboard_hand_half_width_max", 0.40))
        self.half_height_ratio = float(self.config.get("keyboard_hand_height_ratio", 0.72))
        self.half_upward_bias = float(self.config.get("keyboard_hand_upward_bias", 0.70))
        self.half_vertical_offset = float(self.config.get("keyboard_hand_vertical_offset", -0.015))
        self.half_horizontal_offset_left = float(self.config.get("keyboard_hand_horizontal_offset_left", 0.0))
        self.half_horizontal_offset_right = float(self.config.get("keyboard_hand_horizontal_offset_right", 0.0))
        self.half_vertical_offset_left = float(self.config.get("keyboard_hand_vertical_offset_left", self.half_vertical_offset))
        self.half_vertical_offset_right = float(self.config.get("keyboard_hand_vertical_offset_right", self.half_vertical_offset))
        self.finger_anchor_row = float(self.config.get("keyboard_finger_anchor_row", 0.20))
        self.finger_anchor_mix_x = float(self.config.get("keyboard_finger_anchor_mix_x", 0.92))
        self.finger_anchor_mix_y = float(self.config.get("keyboard_finger_anchor_mix_y", 0.90))
        self.drag_deadzone_margin_x = float(self.config.get("keyboard_drag_deadzone_margin_x", 0.14))
        self.drag_deadzone_margin_y = float(self.config.get("keyboard_drag_deadzone_margin_y", 0.18))
        self.size_ema_alpha = float(self.config.get("keyboard_hand_size_ema_alpha", 0.22))

        self.debug_enabled = bool(self.config.get("debug_mode", False))
        self._debug_log_interval_sec = float(self.config.get("keyboard_debug_log_interval_sec", 0.8))

        # Forward-poke v2 typing model
        self.keyboard_v2_enabled = bool(self.config.get("keyboard_v2_enabled", True))
        self.v2_active_fingers = self.config.get("keyboard_v2_active_fingers", ["index"])
        if not isinstance(self.v2_active_fingers, list) or not self.v2_active_fingers:
            self.v2_active_fingers = ["index"]
        self.v2_calibration_ms = int(self.config.get("keyboard_v2_calibration_ms", 2000))
        self.v2_target_lock_frames = int(self.config.get("keyboard_v2_target_lock_frames", 3))
        self.v2_press_displacement = self.config.get("keyboard_v2_press_displacement", None)
        self.v2_press_velocity = self.config.get("keyboard_v2_press_velocity", None)
        self.v2_release_displacement = self.config.get("keyboard_v2_release_displacement", None)
        self.v2_max_lateral_drift_ratio = float(self.config.get("keyboard_v2_max_lateral_drift_ratio", 0.28))
        self.v2_min_refractory_ms = int(self.config.get("keyboard_v2_min_refractory_ms", 80))
        self.v2_global_min_interval_ms = int(self.config.get("keyboard_v2_global_min_interval_ms", 20))
        self.v2_rearm_frames = int(self.config.get("keyboard_v2_rearm_frames", 2))
        self.v2_modifier_hold_ms = int(self.config.get("keyboard_v2_modifier_hold_ms", 120))
        self.v2_key_sticky_margin = float(self.config.get("keyboard_key_sticky_margin", 0.10))
        self.v2_simple_forward_tap = bool(self.config.get("keyboard_v2_simple_forward_tap", True))
        # Deprecated compatibility flag; simple mode now always requires velocity + forward displacement.
        self.v2_simple_velocity_only = bool(self.config.get("keyboard_v2_simple_velocity_only", False))
        self.v2_simple_baseline_alpha = float(self.config.get("keyboard_v2_simple_baseline_alpha", 0.18))
        self.v2_simple_release_ratio = float(self.config.get("keyboard_v2_simple_release_ratio", 0.40))
        self.v2_simple_release_floor = float(self.config.get("keyboard_v2_simple_release_floor", 0.0008))
        self.v2_simple_directional_velocity = bool(self.config.get("keyboard_v2_simple_directional_velocity", True))
        self.v2_simple_lateral_velocity_ratio = float(
            self.config.get("keyboard_v2_simple_lateral_velocity_ratio", 0.90)
        )
        self.v2_simple_velocity_window = int(self.config.get("keyboard_v2_simple_velocity_window", 3))
        self.v2_simple_velocity_window = max(1, min(self.v2_simple_velocity_window, 5))
        self.v2_simple_require_camera_forward = bool(
            self.config.get("keyboard_v2_simple_require_camera_forward", True)
        )
        self.v2_simple_camera_disp_ratio = float(
            self.config.get("keyboard_v2_simple_camera_disp_ratio", 0.45)
        )
        self.v2_simple_camera_velocity_ratio = float(
            self.config.get("keyboard_v2_simple_camera_velocity_ratio", 0.45)
        )
        self.v2_simple_forward_lateral_margin = float(
            self.config.get("keyboard_v2_simple_forward_lateral_margin", 0.008)
        )
        self.v2_calibration_min_samples = int(self.config.get("keyboard_v2_calibration_min_samples", 18))
        self.v2_calibration_max_forward_sigma = float(
            self.config.get("keyboard_v2_calibration_max_forward_sigma", 0.020)
        )
        self.v2_calibration_max_lateral_sigma = float(
            self.config.get("keyboard_v2_calibration_max_lateral_sigma", 0.030)
        )
        repeat_keys = self.config.get(
            "keyboard_v2_repeat_keys",
            ["backspace", "arrow_left", "arrow_right", "arrow_up", "arrow_down"],
        )
        if not isinstance(repeat_keys, list):
            repeat_keys = ["backspace", "arrow_left", "arrow_right", "arrow_up", "arrow_down"]
        self.v2_repeat_keys = set(str(k) for k in repeat_keys)

        self._paused = True
        self._status = "Calibrating..."
        self._resume_counter = 0

        self._state_by_finger: Dict[str, FingerRuntime] = {}
        self._held_modifiers = set()
        self._last_event = ""
        self._last_confidence = 0.0
        self._last_debug_log_ts = 0.0
        self._last_global_press_ts = 0.0
        self._single_hand_side_hint: Optional[str] = None

        self._anchor_avg: Dict[str, Optional[Tuple[float, float]]] = {"left": None, "right": None}
        self._size_avg: Dict[str, Optional[Tuple[float, float]]] = {"left": None, "right": None}
        self._overlay_keys = []
        self._active_frames: Dict[str, Optional[HandFrame]] = {"left": None, "right": None}
        self._drag_bounds_by_side: Dict[str, HandFrame] = {}
        self._hovered_slots = set()
        self._overlay_by_id: Dict[str, Dict[str, object]] = {}

        self._state_by_finger_v2: Dict[str, FingerRuntimeV2] = {}
        self._profile_by_finger_v2: Dict[str, FingerProfileV2] = {}
        self._v2_calibration_started_ts: Optional[float] = None
        self._v2_calibrated = False
        self._v2_last_global_press_ts = 0.0
        self._v2_last_now = 0.0

        self._rows_by_side = self._build_split_rows()
        self._rows_unified = self._build_unified_rows()

        if self.keyboard_v2_enabled:
            self._warn_v2_legacy_thresholds_once()
            self._warn_simple_velocity_only_ignored_once()

    def _slot(self, slot_id: str, label: str, key: str, width: float = 1.0) -> Dict[str, object]:
        return {"id": slot_id, "label": label, "key": key, "w": width}

    def _build_split_rows(self) -> Dict[str, List[List[Dict[str, object]]]]:
        left_rows = [
            [
                self._slot("backtick", "`", "backtick"),
                self._slot("1", "1", "1"),
                self._slot("2", "2", "2"),
                self._slot("3", "3", "3"),
                self._slot("4", "4", "4"),
                self._slot("5", "5", "5"),
            ],
            [
                self._slot("tab", "Tab", "tab", 1.4),
                self._slot("q", "Q", "q"),
                self._slot("w", "W", "w"),
                self._slot("e", "E", "e"),
                self._slot("r", "R", "r"),
                self._slot("t", "T", "t"),
            ],
            [
                self._slot("caps_lock", "Caps", "caps_lock", 1.7),
                self._slot("a", "A", "a"),
                self._slot("s", "S", "s"),
                self._slot("d", "D", "d"),
                self._slot("f", "F", "f"),
                self._slot("g", "G", "g"),
            ],
            [
                self._slot("left_shift", "Shift", "left_shift", 2.0),
                self._slot("z", "Z", "z"),
                self._slot("x", "X", "x"),
                self._slot("c", "C", "c"),
                self._slot("v", "V", "v"),
                self._slot("b", "B", "b"),
            ],
            [
                self._slot("left_ctrl", "Ctrl", "left_ctrl", 1.2),
                self._slot("left_win", "Win", "left_win", 1.1),
                self._slot("left_alt", "Alt", "left_alt", 1.1),
                self._slot("left_space", "Space", "space", 3.6),
            ],
        ]

        right_rows = [
            [
                self._slot("6", "6", "6"),
                self._slot("7", "7", "7"),
                self._slot("8", "8", "8"),
                self._slot("9", "9", "9"),
                self._slot("0", "0", "0"),
                self._slot("minus", "-", "minus"),
                self._slot("equals", "=", "equals"),
                self._slot("backspace", "Back", "backspace", 1.8),
            ],
            [
                self._slot("y", "Y", "y"),
                self._slot("u", "U", "u"),
                self._slot("i", "I", "i"),
                self._slot("o", "O", "o"),
                self._slot("p", "P", "p"),
                self._slot("left_bracket", "[", "left_bracket"),
                self._slot("right_bracket", "]", "right_bracket"),
                self._slot("backslash", "\\", "backslash"),
            ],
            [
                self._slot("h", "H", "h"),
                self._slot("j", "J", "j"),
                self._slot("k", "K", "k"),
                self._slot("l", "L", "l"),
                self._slot("semicolon", ";", "semicolon"),
                self._slot("quote", "'", "quote"),
                self._slot("enter", "Enter", "enter", 1.8),
            ],
            [
                self._slot("n", "N", "n"),
                self._slot("m", "M", "m"),
                self._slot("comma", ",", "comma"),
                self._slot("period", ".", "period"),
                self._slot("slash", "/", "slash"),
                self._slot("right_shift", "Shift", "right_shift", 1.8),
            ],
            [
                self._slot("right_space", "Space", "space", 3.6),
                self._slot("right_alt", "Alt", "right_alt", 1.1),
                self._slot("right_win", "Win", "right_win", 1.1),
                self._slot("right_ctrl", "Ctrl", "right_ctrl", 1.2),
            ],
        ]

        return {"left": left_rows, "right": right_rows}

    def _build_unified_rows(self) -> List[List[Dict[str, object]]]:
        return [
            [
                self._slot("backtick", "`", "backtick"),
                self._slot("1", "1", "1"),
                self._slot("2", "2", "2"),
                self._slot("3", "3", "3"),
                self._slot("4", "4", "4"),
                self._slot("5", "5", "5"),
                self._slot("6", "6", "6"),
                self._slot("7", "7", "7"),
                self._slot("8", "8", "8"),
                self._slot("9", "9", "9"),
                self._slot("0", "0", "0"),
                self._slot("minus", "-", "minus"),
                self._slot("equals", "=", "equals"),
                self._slot("backspace", "Back", "backspace", 1.8),
            ],
            [
                self._slot("tab", "Tab", "tab", 1.4),
                self._slot("q", "Q", "q"),
                self._slot("w", "W", "w"),
                self._slot("e", "E", "e"),
                self._slot("r", "R", "r"),
                self._slot("t", "T", "t"),
                self._slot("y", "Y", "y"),
                self._slot("u", "U", "u"),
                self._slot("i", "I", "i"),
                self._slot("o", "O", "o"),
                self._slot("p", "P", "p"),
                self._slot("left_bracket", "[", "left_bracket"),
                self._slot("right_bracket", "]", "right_bracket"),
                self._slot("backslash", "\\", "backslash"),
            ],
            [
                self._slot("caps_lock", "Caps", "caps_lock", 1.7),
                self._slot("a", "A", "a"),
                self._slot("s", "S", "s"),
                self._slot("d", "D", "d"),
                self._slot("f", "F", "f"),
                self._slot("g", "G", "g"),
                self._slot("h", "H", "h"),
                self._slot("j", "J", "j"),
                self._slot("k", "K", "k"),
                self._slot("l", "L", "l"),
                self._slot("semicolon", ";", "semicolon"),
                self._slot("quote", "'", "quote"),
                self._slot("enter", "Enter", "enter", 1.8),
            ],
            [
                self._slot("left_shift", "Shift", "left_shift", 2.0),
                self._slot("z", "Z", "z"),
                self._slot("x", "X", "x"),
                self._slot("c", "C", "c"),
                self._slot("v", "V", "v"),
                self._slot("b", "B", "b"),
                self._slot("n", "N", "n"),
                self._slot("m", "M", "m"),
                self._slot("comma", ",", "comma"),
                self._slot("period", ".", "period"),
                self._slot("slash", "/", "slash"),
                self._slot("right_shift", "Shift", "right_shift", 1.8),
            ],
            [
                self._slot("left_ctrl", "Ctrl", "left_ctrl", 1.2),
                self._slot("left_win", "Win", "left_win", 1.1),
                self._slot("left_alt", "Alt", "left_alt", 1.1),
                self._slot("space", "Space", "space", 6.5),
                self._slot("right_alt", "Alt", "right_alt", 1.1),
                self._slot("right_win", "Win", "right_win", 1.1),
                self._slot("right_ctrl", "Ctrl", "right_ctrl", 1.2),
            ],
        ]

    def _normalized_point(self, point: Optional[Tuple[float, float, float]]) -> Optional[Tuple[float, float, float]]:
        if point is None:
            return None
        x, y, z = point
        if self.flip_x_for_mapping:
            x = 1.0 - x
        return (x, y, z)

    @staticmethod
    def _distance(p1: Tuple[float, float, float], p2: Tuple[float, float, float]) -> float:
        dx = p1[0] - p2[0]
        dy = p1[1] - p2[1]
        dz = p1[2] - p2[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    @staticmethod
    def _clamp(value: float, min_value: float, max_value: float) -> float:
        return max(min_value, min(max_value, value))

    @staticmethod
    def _timestamp_seconds(frame_capture_ts_ns=None) -> float:
        if frame_capture_ts_ns is None:
            return time.time()
        return float(frame_capture_ts_ns) / 1_000_000_000.0

    def _finger_names(self) -> List[str]:
        fingers = [f for f in self.active_fingers if f in {"thumb", "index", "middle", "ring", "pinky"}]
        if not fingers:
            fingers = ["index"]
        if self.use_thumb_fingers:
            if "thumb" not in fingers:
                fingers = ["thumb"] + fingers
        else:
            fingers = [f for f in fingers if f != "thumb"]
        return fingers

    def _finger_names_v2(self) -> List[str]:
        allowed = {"thumb", "index", "middle", "ring", "pinky"}
        fingers = [f for f in self.v2_active_fingers if f in allowed]
        if not fingers:
            fingers = ["index"]
        return fingers

    def _get_hands_by_side(self, coord_space) -> Dict[str, object]:
        left = coord_space.left if coord_space.has_left else None
        right = coord_space.right if coord_space.has_right else None

        if not self.assign_hands_by_x:
            return {"left": left, "right": right}

        if left is None and right is None:
            return {"left": None, "right": None}

        # Single-hand fallback: keep one physical hand on one side only.
        # This avoids duplicate taps where one tracked hand drives both halves.
        if left is None or right is None:
            single = left if left is not None else right
            side_hint = self._single_hand_side_hint if self._single_hand_side_hint in {"left", "right"} else None
            side = side_hint

            wrist = self._normalized_point(single.wrist) if single is not None else None
            if wrist is not None:
                x = wrist[0]
                deadband = self._clamp(self.single_hand_center_deadband, 0.0, 0.25)
                if x < (0.5 - deadband):
                    side = "left"
                elif x > (0.5 + deadband):
                    side = "right"
                elif side is None:
                    side = "left" if x <= 0.5 else "right"

            if side is None:
                side = "left" if left is not None else "right"

            self._single_hand_side_hint = side
            return {"left": single if side == "left" else None, "right": single if side == "right" else None}

        self._single_hand_side_hint = None

        lw = self._normalized_point(left.wrist)
        rw = self._normalized_point(right.wrist)
        if lw is None or rw is None:
            return {"left": left, "right": right}

        if lw[0] <= rw[0]:
            return {"left": left, "right": right}
        return {"left": right, "right": left}

    def _get_state(self, finger_id: str) -> FingerRuntime:
        if finger_id not in self._state_by_finger:
            self._state_by_finger[finger_id] = FingerRuntime()
        return self._state_by_finger[finger_id]

    def _get_state_v2(self, finger_id: str) -> FingerRuntimeV2:
        if finger_id not in self._state_by_finger_v2:
            self._state_by_finger_v2[finger_id] = FingerRuntimeV2()
        return self._state_by_finger_v2[finger_id]

    def _get_profile_v2(self, finger_id: str) -> FingerProfileV2:
        if finger_id not in self._profile_by_finger_v2:
            self._profile_by_finger_v2[finger_id] = FingerProfileV2()
        return self._profile_by_finger_v2[finger_id]

    @staticmethod
    def _reset_v2_runtime(state: FingerRuntimeV2):
        state.phase = FingerPhaseV2.MISSING
        state.hover_slot_id = None
        state.lock_slot_id = None
        state.lock_action_key = None
        state.lock_frames = 0
        state.active_slot_id = None
        state.active_action_key = None
        state.modifier_held = False
        state.rearm_frames = 0
        state.last_forward = 0.0
        state.last_velocity = 0.0
        state.last_ts = None
        state.press_confidence = 0.0
        state.forward_disp = 0.0
        state.lateral_disp = 0.0
        state.normalized_forward = 0.0
        state.baseline_z = None
        state.baseline_tip = None
        state.last_tip = None
        state.lateral_velocity = 0.0
        state.camera_forward_disp = 0.0
        state.camera_forward_velocity = 0.0
        state.forward_velocity_samples.clear()
        state.lateral_velocity_samples.clear()
        state.camera_forward_velocity_samples.clear()

    @staticmethod
    def _vector_sub(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    @staticmethod
    def _vector_scale(a: Tuple[float, float, float], s: float) -> Tuple[float, float, float]:
        return (a[0] * s, a[1] * s, a[2] * s)

    @staticmethod
    def _vector_dot(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
        return (a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2])

    @staticmethod
    def _vector_norm(a: Tuple[float, float, float]) -> float:
        return math.sqrt((a[0] * a[0]) + (a[1] * a[1]) + (a[2] * a[2]))

    def _v2_smooth_velocity(self, samples: deque, value: float) -> float:
        samples.append(float(value))
        while len(samples) > self.v2_simple_velocity_window:
            samples.popleft()
        if len(samples) >= 3:
            ordered = sorted(samples)
            mid = len(ordered) // 2
            if len(ordered) % 2:
                return ordered[mid]
            return 0.5 * (ordered[mid - 1] + ordered[mid])
        return sum(samples) / max(len(samples), 1)

    def _warn_v2_legacy_thresholds_once(self):
        if AirTypingGesture._legacy_v2_warning_emitted:
            return
        AirTypingGesture._legacy_v2_warning_emitted = True
        print(
            "[AIRTYPE] keyboard_v2_enabled=True; legacy keyboard_press_* and keyboard_release_* "
            "tap thresholds are ignored."
        )

    def _warn_simple_velocity_only_ignored_once(self):
        if not self.v2_simple_velocity_only:
            return
        if AirTypingGesture._simple_velocity_only_warning_emitted:
            return
        AirTypingGesture._simple_velocity_only_warning_emitted = True
        print(
            "[AIRTYPE] keyboard_v2_simple_velocity_only is deprecated and ignored; "
            "simple tap now requires forward velocity + small positive forward displacement."
        )

    def _both_hands_present(self, hands_data: HandsData) -> bool:
        return hands_data.camera.has_left and hands_data.camera.has_right

    def _compute_hand_frame(self, side: str, hand) -> Optional[HandFrame]:
        if hand is None or not hand.exists or hand.wrist is None:
            return None

        wrist = self._normalized_point(hand.wrist)
        if wrist is None:
            return None

        fingertip_points = []
        for finger_name in ("index", "middle", "ring", "pinky"):
            tip = self._get_tip(hand, finger_name)
            if tip is not None:
                fingertip_points.append(tip)

        if fingertip_points:
            avg_tip_x = sum(p[0] for p in fingertip_points) / len(fingertip_points)
            avg_tip_y = sum(p[1] for p in fingertip_points) / len(fingertip_points)
            anchor_x_raw = (self.finger_anchor_mix_x * avg_tip_x) + ((1.0 - self.finger_anchor_mix_x) * wrist[0])
            anchor_y_raw = (self.finger_anchor_mix_y * avg_tip_y) + ((1.0 - self.finger_anchor_mix_y) * wrist[1])
        else:
            # Fallback when fingertips are temporarily occluded.
            anchor_x_raw = wrist[0]
            anchor_y_raw = wrist[1]

        prev_anchor = self._anchor_avg.get(side)
        if prev_anchor is None:
            anchor_x = anchor_x_raw
            anchor_y = anchor_y_raw
        else:
            a = self.wrist_ema_alpha
            anchor_x = prev_anchor[0] * (1.0 - a) + anchor_x_raw * a
            anchor_y = prev_anchor[1] * (1.0 - a) + anchor_y_raw * a
        self._anchor_avg[side] = (anchor_x, anchor_y)

        index_base = self._normalized_point(hand.index.base)
        pinky_base = self._normalized_point(hand.pinky.base)
        span = 0.14
        if index_base is not None and pinky_base is not None:
            span = max(self._distance(index_base, pinky_base), 0.08)

        tip_span_x = 0.10
        if len(fingertip_points) >= 2:
            min_tip_x = min(p[0] for p in fingertip_points)
            max_tip_x = max(p[0] for p in fingertip_points)
            tip_span_x = max(0.06, max_tip_x - min_tip_x)

        finger_reach = 0.18
        if fingertip_points:
            finger_reach = max(
                0.12,
                sum(self._distance(tip, wrist) for tip in fingertip_points) / len(fingertip_points),
            )

        width_raw = max(
            span * self.half_width_scale,
            tip_span_x * 2.8,
            finger_reach * 1.35,
        )
        width = self._clamp(width_raw, self.half_width_min, self.half_width_max)
        height = self._clamp(width * self.half_height_ratio, 0.15, 0.55)

        prev_size = self._size_avg.get(side)
        if prev_size is not None:
            sa = self.size_ema_alpha
            width = prev_size[0] * (1.0 - sa) + width * sa
            height = prev_size[1] * (1.0 - sa) + height * sa
        self._size_avg[side] = (width, height)

        # Place the keyboard so fingertips sit on upper rows (not near the wrist).
        vertical_offset = self.half_vertical_offset_left if side == "left" else self.half_vertical_offset_right
        horizontal_offset = self.half_horizontal_offset_left if side == "left" else self.half_horizontal_offset_right

        top_raw = anchor_y - (height * self.finger_anchor_row) + vertical_offset
        center_x = self._clamp(anchor_x + horizontal_offset, width / 2.0, 1.0 - width / 2.0)
        center_y = self._clamp(top_raw + (height / 2.0), height / 2.0, 1.0 - height / 2.0)

        left = center_x - width / 2.0
        top = center_y - height / 2.0
        return HandFrame(left=left, top=top, width=width, height=height)

    def _slot_from_uv(self, side: str, u: float, v: float) -> Optional[Dict[str, object]]:
        if u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0:
            return None

        if self.keyboard_split_layout:
            rows = self._rows_by_side.get(side, [])
        else:
            rows = self._rows_unified

        if not rows:
            return None
        row_count = len(rows)
        row_idx = min(row_count - 1, max(0, int(v * row_count)))
        row = rows[row_idx]

        total_w = sum(float(slot["w"]) for slot in row)
        if total_w <= 1e-6:
            return None

        x_units = u * total_w
        accum = 0.0
        for slot in row:
            next_accum = accum + float(slot["w"])
            if x_units <= next_accum:
                return slot
            accum = next_accum

        return row[-1] if row else None

    def _map_tip_to_slot(self, side: str, tip: Tuple[float, float, float], frame: HandFrame) -> Optional[Dict[str, object]]:
        if frame.width <= 1e-6 or frame.height <= 1e-6:
            return None

        u = (tip[0] - frame.left) / frame.width
        v = (tip[1] - frame.top) / frame.height
        return self._slot_from_uv(side, u, v)

    def _map_tip_to_any_slot(self, tip: Tuple[float, float, float]) -> Optional[Dict[str, object]]:
        """
        Map a fingertip to whichever rendered key rectangle contains it, regardless of side.
        This matches the on-screen keyboard bounds directly.
        """
        x = tip[0]
        y = tip[1]
        best: Optional[Tuple[float, str]] = None
        for rect in self._overlay_keys:
            rx = float(rect["x"])
            ry = float(rect["y"])
            rw = float(rect["w"])
            rh = float(rect["h"])
            margin_x = 0.0
            margin_y = 0.0
            if not ((rx - margin_x) <= x <= (rx + rw + margin_x)):
                continue
            if not ((ry - margin_y) <= y <= (ry + rh + margin_y)):
                continue

            cx = rx + (rw * 0.5)
            cy = ry + (rh * 0.5)
            d2 = ((x - cx) * (x - cx)) + ((y - cy) * (y - cy))
            slot_id = str(rect["id"])
            if best is None or d2 < best[0]:
                best = (d2, slot_id)

        if best is None:
            return None
        return self._slot_definition_by_id(best[1])

    def _slot_definition_by_id(self, slot_id: str) -> Optional[Dict[str, object]]:
        for side in ("left", "right"):
            for row in self._rows_by_side.get(side, []):
                for slot in row:
                    if str(slot.get("id")) == slot_id:
                        return slot
        for row in self._rows_unified:
            for slot in row:
                if str(slot.get("id")) == slot_id:
                    return slot
        return None

    def _get_tip(self, hand, finger_name: str) -> Optional[Tuple[float, float, float]]:
        if hand is None or not hand.exists:
            return None
        finger = getattr(hand, finger_name, None)
        if finger is None or finger.tip is None:
            return None
        return self._normalized_point(finger.tip)

    def _get_finger_bend_radius(self, wrist_hand, finger_name: str) -> Tuple[Optional[float], Optional[float]]:
        if wrist_hand is None or not wrist_hand.exists:
            return None, None

        finger = getattr(wrist_hand, finger_name, None)
        if finger is None or finger.tip is None:
            return None, None

        angle = get_finger_angle(finger)
        bend = max(0.0, 180.0 - angle)

        tip = self._normalized_point(finger.tip)
        if tip is None:
            return None, None

        radius = math.sqrt(tip[0] * tip[0] + tip[1] * tip[1] + tip[2] * tip[2])
        return bend, radius

    def _v2_finger_ids_for_hands(self, camera_hands: Dict[str, object]) -> List[str]:
        ids = []
        for side in ("left", "right"):
            hand = camera_hands.get(side)
            if hand is None or not hand.exists:
                if not self.require_both_hands:
                    continue
            for finger_name in self._finger_names_v2():
                ids.append(f"{side}_{finger_name}")
        return ids

    def _palm_axis_toward_camera(self, camera_hand) -> Tuple[float, float, float]:
        if camera_hand is None or not camera_hand.exists or camera_hand.wrist is None:
            return (0.0, 0.0, -1.0)

        wrist = self._normalized_point(camera_hand.wrist)
        index_base = self._normalized_point(camera_hand.index.base)
        pinky_base = self._normalized_point(camera_hand.pinky.base)
        if wrist is None or index_base is None or pinky_base is None:
            return (0.0, 0.0, -1.0)

        v1 = self._vector_sub(index_base, wrist)
        v2 = self._vector_sub(pinky_base, wrist)
        normal = (
            (v1[1] * v2[2]) - (v1[2] * v2[1]),
            (v1[2] * v2[0]) - (v1[0] * v2[2]),
            (v1[0] * v2[1]) - (v1[1] * v2[0]),
        )
        mag = self._vector_norm(normal)
        if mag <= 1e-6:
            return (0.0, 0.0, -1.0)

        axis = (normal[0] / mag, normal[1] / mag, normal[2] / mag)
        # Positive press displacement should correspond to movement toward camera (lower z).
        if axis[2] > 0.0:
            axis = (-axis[0], -axis[1], -axis[2])
        return axis

    @staticmethod
    def _sigma(values: List[float], floor: float = 0.0) -> float:
        if not values:
            return floor
        mean = sum(values) / len(values)
        variance = sum((v - mean) * (v - mean) for v in values) / len(values)
        return max(floor, math.sqrt(max(0.0, variance)))

    def _v2_start_calibration_if_needed(self, now: float):
        if self._v2_calibrated:
            return
        if self._v2_calibration_started_ts is None:
            self._v2_calibration_started_ts = now
            self._status = "Keyboard Calibrating (Forward Poke)..."

    def _v2_calibration_progress(self, now: float) -> float:
        if self._v2_calibration_started_ts is None:
            return 0.0
        duration_s = max(self.v2_calibration_ms / 1000.0, 1e-3)
        return self._clamp((now - self._v2_calibration_started_ts) / duration_s, 0.0, 1.0)

    def _v2_collect_calibration_sample(
        self,
        finger_id: str,
        tip: Tuple[float, float, float],
        axis: Tuple[float, float, float],
        now: float,
    ):
        profile = self._get_profile_v2(finger_id)
        profile.samples.append((tip, axis, now))

    def _v2_finalize_profile(self, profile: FingerProfileV2) -> bool:
        if len(profile.samples) < self.v2_calibration_min_samples:
            return False

        mean_tip = (
            sum(sample[0][0] for sample in profile.samples) / len(profile.samples),
            sum(sample[0][1] for sample in profile.samples) / len(profile.samples),
            sum(sample[0][2] for sample in profile.samples) / len(profile.samples),
        )
        forward_values: List[float] = []
        lateral_values: List[float] = []
        velocity_values: List[float] = []
        last_forward = None
        last_ts = None
        for tip, axis, ts in profile.samples:
            disp = self._vector_sub(tip, mean_tip)
            forward = self._vector_dot(disp, axis)
            lateral_vec = self._vector_sub(disp, self._vector_scale(axis, forward))
            lateral = self._vector_norm(lateral_vec)
            forward_values.append(forward)
            lateral_values.append(lateral)
            if last_forward is not None and last_ts is not None:
                dt = max(ts - last_ts, 1e-3)
                velocity_values.append((forward - last_forward) / dt)
            last_forward = forward
            last_ts = ts

        forward_sigma = self._sigma(forward_values, floor=1e-4)
        lateral_sigma = self._sigma(lateral_values, floor=1e-4)
        velocity_sigma = self._sigma(velocity_values, floor=1e-4)

        if (
            forward_sigma > self.v2_calibration_max_forward_sigma
            or lateral_sigma > self.v2_calibration_max_lateral_sigma
        ):
            return False

        profile.neutral_tip = mean_tip
        profile.forward_sigma = forward_sigma
        profile.lateral_sigma = lateral_sigma
        profile.velocity_sigma = velocity_sigma
        profile.forward_polarity = 1.0
        profile.forward_polarity_locked = False
        profile.calibrated = True
        profile.samples.clear()
        return True

    def _v2_try_finish_calibration(self, camera_hands: Dict[str, object], now: float) -> bool:
        duration_s = max(self.v2_calibration_ms / 1000.0, 1e-3)
        if self._v2_calibration_started_ts is None:
            return False
        if (now - self._v2_calibration_started_ts) < duration_s:
            return False

        required_ids = self._v2_finger_ids_for_hands(camera_hands)
        if not required_ids:
            return False

        calibrated_ids = set()
        for finger_id in required_ids:
            profile = self._get_profile_v2(finger_id)
            if profile.calibrated:
                calibrated_ids.add(finger_id)
                continue
            if self._v2_finalize_profile(profile):
                calibrated_ids.add(finger_id)

        if not calibrated_ids:
            return False

        if self.require_both_hands:
            left_ready = any(finger_id.startswith("left_") for finger_id in calibrated_ids)
            right_ready = any(finger_id.startswith("right_") for finger_id in calibrated_ids)
            if not (left_ready and right_ready):
                return False

        self._v2_calibrated = True
        self._status = f"Keyboard Ready (Forward Poke {len(calibrated_ids)}/{len(required_ids)})"
        return True

    def _v2_press_displacement_threshold(self, profile: FingerProfileV2) -> float:
        if self.v2_press_displacement is not None:
            try:
                value = float(self.v2_press_displacement)
                if value > 0.0:
                    return value
            except Exception:
                pass
        adaptive = 0.0025 + (2.8 * profile.forward_sigma)
        return self._clamp(adaptive, 0.0030, 0.030)

    def _v2_press_velocity_threshold(self, profile: FingerProfileV2) -> float:
        if self.v2_press_velocity is not None:
            try:
                value = float(self.v2_press_velocity)
                if value >= 0.0:
                    return value
            except Exception:
                pass
        adaptive = 0.020 + (2.2 * profile.velocity_sigma)
        return self._clamp(adaptive, 0.030, 0.70)

    def _v2_release_displacement_threshold(self, press_threshold: float, profile: FingerProfileV2) -> float:
        if self.v2_release_displacement is not None:
            try:
                value = float(self.v2_release_displacement)
                if value > 0.0:
                    return value
            except Exception:
                pass
        adaptive = (2.2 * profile.forward_sigma) + 0.001
        return min(press_threshold * 0.60, max(adaptive, press_threshold * 0.35))

    def _v2_lateral_limit(self, slot_id: Optional[str], profile: FingerProfileV2) -> float:
        rect = self._overlay_by_id.get(slot_id or "")
        if rect is None:
            key_scale = 0.045
        else:
            key_scale = min(float(rect["w"]), float(rect["h"]))
        base = key_scale * self.v2_max_lateral_drift_ratio
        return max(base, (3.0 * profile.lateral_sigma) + 0.0035)

    def _v2_tip_within_lock_bounds(self, tip: Tuple[float, float, float], slot_id: Optional[str]) -> bool:
        if slot_id is None:
            return False
        rect = self._overlay_by_id.get(slot_id)
        if rect is None:
            return False
        margin_x = max(0.002, float(rect["w"]) * self.v2_key_sticky_margin)
        margin_y = max(0.002, float(rect["h"]) * self.v2_key_sticky_margin)
        x = tip[0]
        y = tip[1]
        return (
            (float(rect["x"]) - margin_x) <= x <= (float(rect["x"]) + float(rect["w"]) + margin_x)
            and (float(rect["y"]) - margin_y) <= y <= (float(rect["y"]) + float(rect["h"]) + margin_y)
        )

    def _v2_update_finger_metrics(
        self,
        state: FingerRuntimeV2,
        profile: FingerProfileV2,
        tip: Tuple[float, float, float],
        axis: Tuple[float, float, float],
        now: float,
    ):
        neutral_tip = profile.neutral_tip
        if neutral_tip is None:
            state.forward_disp = 0.0
            state.lateral_disp = 0.0
            state.last_velocity = 0.0
            return

        disp = self._vector_sub(tip, neutral_tip)
        raw_forward = self._vector_dot(disp, axis)
        lateral_vec = self._vector_sub(disp, self._vector_scale(axis, raw_forward))
        lateral = self._vector_norm(lateral_vec)
        polarity = -1.0 if profile.forward_polarity < 0.0 else 1.0
        forward = raw_forward * polarity

        velocity = 0.0
        if state.last_ts is not None:
            dt = max(now - state.last_ts, 1e-3)
            velocity = (forward - state.last_forward) / dt

        state.forward_disp = forward
        state.lateral_disp = lateral
        state.last_velocity = velocity
        state.last_forward = forward
        state.last_ts = now

    def _v2_maybe_lock_forward_polarity(
        self,
        profile: FingerProfileV2,
        state: FingerRuntimeV2,
        press_disp_threshold: float,
        press_vel_threshold: float,
        lateral_limit: float,
    ):
        if profile.forward_polarity_locked:
            return

        if state.lateral_disp > (lateral_limit * 1.10):
            return

        # Wait for a clear poke-like motion before committing a forward polarity.
        if abs(state.forward_disp) < max(press_disp_threshold * 1.20, 0.0025):
            return
        if abs(state.last_velocity) < max(press_vel_threshold * 0.80, 0.04):
            return

        if state.forward_disp < 0.0:
            profile.forward_polarity = -1.0
            state.forward_disp = -state.forward_disp
            state.last_forward = -state.last_forward
            state.last_velocity = -state.last_velocity

        profile.forward_polarity_locked = True

    def _v2_should_press(
        self,
        state: FingerRuntimeV2,
        forward_disp: float,
        forward_velocity: float,
        lateral_disp: float,
        press_disp_threshold: float,
        press_vel_threshold: float,
        lateral_limit: float,
        now: float,
    ) -> bool:
        refractory = self.v2_min_refractory_ms / 1000.0
        global_interval = self.v2_global_min_interval_ms / 1000.0
        if (now - state.last_press_ts) < refractory:
            return False
        if (now - self._v2_last_global_press_ts) < global_interval:
            return False
        if forward_disp < press_disp_threshold:
            return False
        if lateral_disp > (lateral_limit * 1.25):
            return False
        velocity_gate = forward_velocity >= press_vel_threshold
        deep_gate = forward_disp >= (press_disp_threshold * 1.45)
        if not (velocity_gate or deep_gate):
            return False
        return True

    @staticmethod
    def _v2_should_release(
        forward_disp: float,
        forward_velocity: float,
        release_disp_threshold: float,
    ) -> bool:
        return forward_disp <= release_disp_threshold and forward_velocity <= 0.025

    def _v2_reset_missing_side(self, side: str):
        for finger_name in self._finger_names_v2():
            finger_id = f"{side}_{finger_name}"
            state = self._state_by_finger_v2.get(finger_id)
            if state is None:
                continue
            if state.phase == FingerPhaseV2.PRESSED:
                self._v2_process_release(state)
            self._reset_v2_runtime(state)

    def _v2_process_press(
        self,
        state: FingerRuntimeV2,
        slot: Dict[str, object],
        confidence: float,
        now: float,
        press_velocity: Optional[float] = None,
    ):
        action_key = str(slot["key"])
        state.phase = FingerPhaseV2.PRESSED
        state.active_slot_id = str(slot["id"])
        state.active_action_key = action_key
        state.last_press_ts = now
        state.last_repeat_ts = now
        state.press_confidence = confidence
        state.modifier_held = False
        self._last_confidence = confidence
        self._v2_last_global_press_ts = now
        effective_velocity = state.last_velocity if press_velocity is None else press_velocity
        print(
            "[AIRTYPE-V2-PRESS] "
            f"key={action_key} press_velocity={effective_velocity:.4f} confidence={confidence:.3f}"
        )

        if action_key in MODIFIER_KEYS:
            self._last_event = f"modifier_armed:{action_key}"
            return
        self._tap_key(action_key)

    def _v2_process_release(self, state: FingerRuntimeV2):
        if state.modifier_held and state.active_action_key in MODIFIER_KEYS:
            self._key_up(state.active_action_key)
        state.phase = FingerPhaseV2.RELEASE_WAIT
        state.active_slot_id = None
        state.active_action_key = None
        state.modifier_held = False
        state.rearm_frames = 0
        state.press_confidence = 0.0

    def _maybe_repeat_v2(self, state: FingerRuntimeV2, now: float) -> bool:
        key = state.active_action_key
        if key is None or key not in self.v2_repeat_keys:
            return False
        repeat_delay = self.repeat_delay_ms / 1000.0
        repeat_interval = 1.0 / max(self.repeat_rate_hz, 1)
        if now - state.last_press_ts < repeat_delay:
            return False
        if now - state.last_repeat_ts < repeat_interval:
            return False
        self._tap_key(key)
        state.last_repeat_ts = now
        return True

    def _tap_key(self, key_id: str):
        self.action.tap_key(key_id)
        self._last_event = f"tap:{key_id}"
        if self.debug_enabled:
            print(f"[AIRTYPE] key_tap key={key_id}")

    def _key_down(self, key_id: str):
        self.action.key_down(key_id)
        self._held_modifiers.add(key_id)
        self._last_event = f"down:{key_id}"
        if self.debug_enabled:
            print(f"[AIRTYPE] key_down key={key_id}")

    def _key_up(self, key_id: str):
        self.action.key_up(key_id)
        self._held_modifiers.discard(key_id)
        self._last_event = f"up:{key_id}"
        if self.debug_enabled:
            print(f"[AIRTYPE] key_up key={key_id}")

    def _process_press(self, finger_id: str, slot: Dict[str, object], confidence: float, now: Optional[float] = None):
        state = self._get_state(finger_id)
        action_key = str(slot["key"])

        state.phase = FingerPhase.PRESSED
        state.active_slot_id = str(slot["id"])
        state.active_action_key = action_key
        state.last_press_ts = self._timestamp_seconds() if now is None else now
        state.last_repeat_ts = state.last_press_ts
        state.press_confidence = confidence
        self._last_confidence = confidence

        if action_key in MODIFIER_KEYS:
            self._key_down(action_key)
        elif action_key in LOCK_KEYS:
            self._tap_key(action_key)
        else:
            self._tap_key(action_key)

    def _process_release(self, finger_id: str):
        state = self._get_state(finger_id)
        active_action = state.active_action_key
        if active_action in MODIFIER_KEYS:
            self._key_up(active_action)

        state.phase = FingerPhase.HOVER
        state.active_slot_id = None
        state.active_action_key = None
        state.press_confidence = 0.0

    def _maybe_repeat(self, state: FingerRuntime, now: Optional[float] = None) -> bool:
        if state.active_action_key not in REPEATABLE_KEYS:
            return False

        now = self._timestamp_seconds() if now is None else now
        repeat_delay = self.repeat_delay_ms / 1000.0
        repeat_interval = 1.0 / max(self.repeat_rate_hz, 1)
        if now - state.last_press_ts < repeat_delay:
            return False
        if now - state.last_repeat_ts < repeat_interval:
            return False

        self._tap_key(state.active_action_key)
        state.last_repeat_ts = now
        return True

    def _pause(self, reason: str):
        if self._paused and self._status == reason:
            return

        if self.pause_on_hand_loss:
            self.action.release_all_keys()

        self._held_modifiers.clear()
        self._hovered_slots.clear()

        for state in self._state_by_finger.values():
            state.phase = FingerPhase.HOVER
            state.active_slot_id = None
            state.active_action_key = None
            state.press_confidence = 0.0
            state.hover_slot_id = None
            state.hover_frames = 0
            state.hover_baseline_bend = None
            state.hover_baseline_radius = None
            state.hover_baseline_z = None
            state.last_bend = None
            state.last_radius = None
            state.last_z = None
            state.last_ts = None

        for state in self._state_by_finger_v2.values():
            self._reset_v2_runtime(state)

        if not self._v2_calibrated:
            self._v2_calibration_started_ts = None
            for profile in self._profile_by_finger_v2.values():
                profile.samples.clear()

        self._paused = True
        self._resume_counter = 0
        self._status = reason

    def _resume_if_stable(self, hands_data: HandsData):
        if self.require_both_hands and not self._both_hands_present(hands_data):
            self._pause("Typing Paused: both hands required")
            return False

        self._resume_counter += 1
        if self._resume_counter < self.resume_stability_frames:
            self._status = "Typing Paused: waiting for stable hands..."
            return False

        self._paused = False
        self._status = "Keyboard Ready (Wrist Relative)"
        return False

    def _build_overlay_keys(self, frames: Dict[str, Optional[HandFrame]]) -> List[Dict[str, object]]:
        if not self.keyboard_split_layout:
            frame = self._resolve_unified_frame(frames)
            if frame is None:
                return []

            rows = self._rows_unified
            if not rows:
                return []

            key_rects = []
            row_h = frame.height / len(rows)
            for row_idx, row in enumerate(rows):
                row_top = frame.top + row_h * row_idx
                row_total = sum(float(slot["w"]) for slot in row)
                if row_total <= 1e-6:
                    continue

                accum = 0.0
                for slot in row:
                    slot_w = float(slot["w"]) / row_total
                    x = frame.left + frame.width * accum
                    w = frame.width * slot_w
                    key_rects.append(
                        {
                            "id": str(slot["id"]),
                            "side": "full",
                            "label": str(slot["label"]),
                            "x": x,
                            "y": row_top,
                            "w": w,
                            "h": row_h,
                        }
                    )
                    accum += slot_w

            return key_rects

        key_rects = []
        for side in ("left", "right"):
            frame = frames.get(side)
            if frame is None:
                continue

            rows = self._rows_by_side[side]
            if not rows:
                continue

            row_h = frame.height / len(rows)
            for row_idx, row in enumerate(rows):
                row_top = frame.top + row_h * row_idx
                row_total = sum(float(slot["w"]) for slot in row)
                if row_total <= 1e-6:
                    continue

                accum = 0.0
                for slot in row:
                    slot_w = float(slot["w"]) / row_total
                    x = frame.left + frame.width * accum
                    w = frame.width * slot_w
                    key_rects.append(
                        {
                            "id": str(slot["id"]),
                            "side": side,
                            "label": str(slot["label"]),
                            "x": x,
                            "y": row_top,
                            "w": w,
                            "h": row_h,
                        }
                    )
                    accum += slot_w

        return key_rects

    def _resolve_unified_frame(self, frames: Dict[str, Optional[HandFrame]]) -> Optional[HandFrame]:
        left = frames.get("left")
        right = frames.get("right")

        if left is None and right is None:
            return None

        if left is not None and right is not None:
            left_edge = min(left.left, right.left)
            right_edge = max(left.left + left.width, right.left + right.width)
            width = self._clamp(right_edge - left_edge, 0.30, 0.95)
            center_x = self._clamp((left_edge + right_edge) / 2.0, width / 2.0, 1.0 - (width / 2.0))

            left_center_y = left.top + (left.height / 2.0)
            right_center_y = right.top + (right.height / 2.0)
            center_y = (left_center_y + right_center_y) / 2.0
            height = self._clamp(max(left.height, right.height), 0.15, 0.55)
            center_y = self._clamp(center_y, height / 2.0, 1.0 - (height / 2.0))

            return HandFrame(
                left=center_x - (width / 2.0),
                top=center_y - (height / 2.0),
                width=width,
                height=height,
            )

        source = left if left is not None else right
        source_center_x = source.left + (source.width / 2.0)
        source_center_y = source.top + (source.height / 2.0)
        width = self._clamp(source.width * 2.05, 0.30, 0.95)
        height = self._clamp(max(source.height, width * 0.34), 0.15, 0.55)
        center_x = self._clamp(source_center_x, width / 2.0, 1.0 - (width / 2.0))
        center_y = self._clamp(source_center_y, height / 2.0, 1.0 - (height / 2.0))
        return HandFrame(
            left=center_x - (width / 2.0),
            top=center_y - (height / 2.0),
            width=width,
            height=height,
        )

    def _set_overlay_keys(self, key_rects: List[Dict[str, object]]):
        self._overlay_keys = key_rects
        self._overlay_by_id = {str(key["id"]): key for key in key_rects}

    @staticmethod
    def _copy_frame(frame: Optional[HandFrame]) -> Optional[HandFrame]:
        if frame is None:
            return None
        return HandFrame(left=frame.left, top=frame.top, width=frame.width, height=frame.height)

    @staticmethod
    def _frame_center(frame: HandFrame) -> Tuple[float, float]:
        return (frame.left + (frame.width / 2.0), frame.top + (frame.height / 2.0))

    def _compute_deadzone_frame(self, frame: HandFrame) -> HandFrame:
        margin_x = max(0.0, frame.width * self.drag_deadzone_margin_x)
        margin_y = max(0.0, frame.height * self.drag_deadzone_margin_y)
        width = min(1.0, frame.width + (2.0 * margin_x))
        height = min(1.0, frame.height + (2.0 * margin_y))

        center_x, center_y = self._frame_center(frame)
        center_x = self._clamp(center_x, width / 2.0, 1.0 - (width / 2.0))
        center_y = self._clamp(center_y, height / 2.0, 1.0 - (height / 2.0))

        return HandFrame(
            left=center_x - (width / 2.0),
            top=center_y - (height / 2.0),
            width=width,
            height=height,
        )

    def _update_drag_bounds(self, frames: Dict[str, Optional[HandFrame]]):
        self._drag_bounds_by_side = {}
        if not self.keyboard_split_layout:
            unified_frame = self._resolve_unified_frame(frames)
            if unified_frame is not None:
                self._drag_bounds_by_side["full"] = self._compute_deadzone_frame(unified_frame)
            return

        for side in ("left", "right"):
            frame = frames.get(side)
            if frame is None:
                continue
            self._drag_bounds_by_side[side] = self._compute_deadzone_frame(frame)

    def _update_active_frames(
        self,
        candidate_frames: Dict[str, Optional[HandFrame]],
        recenter: bool,
    ):
        for side in ("left", "right"):
            candidate = candidate_frames.get(side)
            active = self._active_frames.get(side)

            if active is None and candidate is not None:
                self._active_frames[side] = self._copy_frame(candidate)
                continue

            if recenter:
                if candidate is not None:
                    self._active_frames[side] = self._copy_frame(candidate)
                continue

            if candidate is None or active is None:
                continue

            candidate_center_x, candidate_center_y = self._frame_center(candidate)
            deadzone = self._compute_deadzone_frame(active)
            deadzone_right = deadzone.left + deadzone.width
            deadzone_bottom = deadzone.top + deadzone.height

            shift_x = 0.0
            shift_y = 0.0
            if candidate_center_x < deadzone.left:
                shift_x = candidate_center_x - deadzone.left
            elif candidate_center_x > deadzone_right:
                shift_x = candidate_center_x - deadzone_right

            if candidate_center_y < deadzone.top:
                shift_y = candidate_center_y - deadzone.top
            elif candidate_center_y > deadzone_bottom:
                shift_y = candidate_center_y - deadzone_bottom

            if abs(shift_x) <= 1e-6 and abs(shift_y) <= 1e-6:
                continue

            active_center_x, active_center_y = self._frame_center(active)
            new_center_x = self._clamp(
                active_center_x + shift_x,
                active.width / 2.0,
                1.0 - (active.width / 2.0),
            )
            new_center_y = self._clamp(
                active_center_y + shift_y,
                active.height / 2.0,
                1.0 - (active.height / 2.0),
            )
            self._active_frames[side] = HandFrame(
                left=new_center_x - (active.width / 2.0),
                top=new_center_y - (active.height / 2.0),
                width=active.width,
                height=active.height,
            )

    def _fallback_overlay_frames(self) -> Dict[str, Optional[HandFrame]]:
        """
        Provide a stable split-keyboard frame when hand-derived frames are unavailable.
        """
        full_center_x = float(self.config.get("keyboard_fixed_center_x", 0.5))
        full_center_y = float(self.config.get("keyboard_fixed_center_y", 0.58))
        full_width = float(self.config.get("keyboard_fixed_width", 0.78))
        full_height = float(self.config.get("keyboard_fixed_height", 0.26))

        full_width = self._clamp(full_width, 0.35, 0.95)
        full_height = self._clamp(full_height, 0.12, 0.55)
        half_gap = max(0.01, full_width * 0.025)
        half_width = max(0.10, (full_width - half_gap) / 2.0)

        center_y = self._clamp(full_center_y, full_height / 2.0, 1.0 - (full_height / 2.0))
        left_center_x = self._clamp(
            full_center_x - ((half_width + half_gap) / 2.0),
            half_width / 2.0,
            1.0 - (half_width / 2.0),
        )
        right_center_x = self._clamp(
            full_center_x + ((half_width + half_gap) / 2.0),
            half_width / 2.0,
            1.0 - (half_width / 2.0),
        )

        return {
            "left": HandFrame(
                left=left_center_x - (half_width / 2.0),
                top=center_y - (full_height / 2.0),
                width=half_width,
                height=full_height,
            ),
            "right": HandFrame(
                left=right_center_x - (half_width / 2.0),
                top=center_y - (full_height / 2.0),
                width=half_width,
                height=full_height,
            ),
        }

    def _spread_overlay_frames(
        self,
        frames: Dict[str, Optional[HandFrame]],
        hands_data: HandsData,
    ) -> Dict[str, Optional[HandFrame]]:
        """
        Ensure overlay shows two visible keyboard halves.

        When only one hand is detected (or both frames overlap heavily due hand-loss fallback),
        synthesize separated left/right frames for UI rendering only.
        """
        left = frames.get("left")
        right = frames.get("right")

        if left is None and right is None:
            return frames

        if left is not None and right is not None:
            left_cx = left.left + (left.width / 2.0)
            right_cx = right.left + (right.width / 2.0)
            avg_width = (left.width + right.width) / 2.0
            min_separation = avg_width * 0.35

            # Keep naturally separated two-hand overlay untouched.
            if abs(right_cx - left_cx) >= min_separation:
                return frames

            source_center_x = (left_cx + right_cx) / 2.0
            source_center_y = (
                (left.top + (left.height / 2.0)) + (right.top + (right.height / 2.0))
            ) / 2.0
            width = avg_width
            height = (left.height + right.height) / 2.0
        else:
            source = left if left is not None else right
            source_center_x = source.left + (source.width / 2.0)
            source_center_y = source.top + (source.height / 2.0)
            width = source.width
            height = source.height

        gap = max(0.02, width * 0.10)
        left_center_x = self._clamp(source_center_x - ((width + gap) / 2.0), width / 2.0, 1.0 - (width / 2.0))
        right_center_x = self._clamp(source_center_x + ((width + gap) / 2.0), width / 2.0, 1.0 - (width / 2.0))
        center_y = self._clamp(source_center_y, height / 2.0, 1.0 - (height / 2.0))

        return {
            "left": HandFrame(
                left=left_center_x - (width / 2.0),
                top=center_y - (height / 2.0),
                width=width,
                height=height,
            ),
            "right": HandFrame(
                left=right_center_x - (width / 2.0),
                top=center_y - (height / 2.0),
                width=width,
                height=height,
            ),
        }

    def _v2_simple_press_displacement_threshold(self) -> float:
        if self.v2_press_displacement is not None:
            try:
                value = float(self.v2_press_displacement)
                if value > 0.0:
                    return value
            except Exception:
                pass
        return 0.0015

    def _v2_simple_press_velocity_threshold(self) -> float:
        if self.v2_press_velocity is not None:
            try:
                value = float(self.v2_press_velocity)
                if value >= 0.0:
                    return value
            except Exception:
                pass
        return 0.0

    def _v2_simple_release_displacement_threshold(self, press_threshold: float) -> float:
        if self.v2_release_displacement is not None:
            try:
                value = float(self.v2_release_displacement)
                if value > 0.0:
                    return value
            except Exception:
                pass
        return max(self.v2_simple_release_floor, press_threshold * self.v2_simple_release_ratio)

    def _v2_simple_should_press(
        self,
        state: FingerRuntimeV2,
        forward_disp: float,
        forward_velocity: float,
        press_disp_threshold: float,
        press_vel_threshold: float,
        now: float,
        lateral_velocity: float = 0.0,
        camera_forward_disp: Optional[float] = None,
        camera_forward_velocity: Optional[float] = None,
        return_reason: bool = False,
    ):
        def _result(ok: bool, reason: str):
            if return_reason:
                return ok, reason
            return ok

        refractory = self.v2_min_refractory_ms / 1000.0
        global_interval = self.v2_global_min_interval_ms / 1000.0
        if (now - state.last_press_ts) < refractory:
            return _result(False, "refractory")
        if (now - self._v2_last_global_press_ts) < global_interval:
            return _result(False, "global_interval")

        # Velocity is the primary signal, but require a small positive forward displacement
        # to suppress rebound/sweep spikes being mistaken as presses.
        min_forward_disp = max(0.0, press_disp_threshold)
        if forward_disp < min_forward_disp:
            return _result(False, "forward_disp")

        if press_vel_threshold > 0.0 and forward_velocity < press_vel_threshold:
            return _result(False, "forward_velocity")

        # Secondary camera-depth gate to reject wrist-rotation artifacts when the fingertip
        # is not actually moving toward the camera (common at low FPS).
        if camera_forward_disp is None:
            camera_forward_disp = forward_disp
        if camera_forward_velocity is None:
            camera_forward_velocity = forward_velocity
        if self.v2_simple_require_camera_forward:
            camera_disp_floor = max(0.0, min_forward_disp * max(0.0, self.v2_simple_camera_disp_ratio))
            if camera_forward_disp < camera_disp_floor:
                return _result(False, "camera_forward_disp")
            if press_vel_threshold > 0.0:
                camera_vel_floor = max(0.0, press_vel_threshold * max(0.0, self.v2_simple_camera_velocity_ratio))
                if camera_forward_velocity < camera_vel_floor:
                    return _result(False, "camera_forward_velocity")

        if self.v2_simple_directional_velocity:
            ratio = max(0.0, self.v2_simple_lateral_velocity_ratio)
            if ratio > 0.0 and lateral_velocity > 0.0 and forward_velocity < (lateral_velocity * ratio):
                return _result(False, "lateral_dominance")
            margin = max(0.0, self.v2_simple_forward_lateral_margin)
            if margin > 0.0 and (forward_velocity - lateral_velocity) < margin:
                return _result(False, "forward_lateral_margin")
        return _result(True, "ok")

    def _v2_simple_resolve_slot(
        self,
        state: FingerRuntimeV2,
        tip: Tuple[float, float, float],
    ) -> Optional[Dict[str, object]]:
        raw_slot = self._map_tip_to_any_slot(tip)
        if state.lock_slot_id and self._v2_tip_within_lock_bounds(tip, state.lock_slot_id):
            sticky_slot = self._slot_definition_by_id(state.lock_slot_id)
            if sticky_slot is not None:
                return sticky_slot
        return raw_slot

    def _update_v2_simple(self, hands_data: HandsData, frame_capture_ts_ns=None):
        """
        Simple forward-tap model:
        if fingertip is inside a key and moves toward camera quickly enough,
        commit that key using velocity as primary signal with a small forward
        displacement requirement to reject lateral/rebound noise.
        """
        action_executed = False

        camera_hands = self._get_hands_by_side(hands_data.camera)
        candidate_frames = {
            "left": self._compute_hand_frame("left", camera_hands.get("left")),
            "right": self._compute_hand_frame("right", camera_hands.get("right")),
        }

        self._update_active_frames(candidate_frames, recenter=self._paused)

        active_frames = self._spread_overlay_frames(self._active_frames, hands_data)
        if active_frames.get("left") is None and active_frames.get("right") is None:
            active_frames = self._fallback_overlay_frames()

        self._set_overlay_keys(self._build_overlay_keys(active_frames))
        self._update_drag_bounds(active_frames)
        unified_frame = self._resolve_unified_frame(active_frames) if not self.keyboard_split_layout else None

        if self.require_both_hands and not self._both_hands_present(hands_data):
            self._pause("Typing Paused: both hands required")
            return False

        if self._paused:
            self._resume_if_stable(hands_data)
            if self._paused:
                return False

        if self.require_both_hands and (
            candidate_frames["left"] is None or candidate_frames["right"] is None
        ):
            self._pause("Typing Paused: both hands required")
            return False

        now = self._timestamp_seconds(frame_capture_ts_ns=frame_capture_ts_ns)
        self._v2_last_now = now
        self._v2_calibrated = True
        hovered_slots = set()
        seen_fingers = set()

        press_disp_threshold = self._v2_simple_press_displacement_threshold()
        press_vel_threshold = self._v2_simple_press_velocity_threshold()
        release_disp_threshold = self._v2_simple_release_displacement_threshold(press_disp_threshold)
        baseline_alpha = self._clamp(self.v2_simple_baseline_alpha, 0.02, 0.50)

        for side in ("left", "right"):
            camera_hand = camera_hands.get(side)
            if camera_hand is None or not camera_hand.exists:
                continue
            axis = self._palm_axis_toward_camera(camera_hand)

            for finger_name in self._finger_names_v2():
                finger_id = f"{side}_{finger_name}"
                seen_fingers.add(finger_id)
                state = self._get_state_v2(finger_id)

                tip = self._get_tip(camera_hand, finger_name)
                if tip is None:
                    if state.phase == FingerPhaseV2.PRESSED:
                        self._v2_process_release(state)
                    self._reset_v2_runtime(state)
                    continue

                slot = self._v2_simple_resolve_slot(state, tip)
                slot_id = str(slot["id"]) if slot is not None else None
                if slot_id is not None:
                    hovered_slots.add(slot_id)

                if slot_id is None:
                    if state.phase == FingerPhaseV2.PRESSED:
                        self._v2_process_release(state)
                    state.phase = FingerPhaseV2.TRACKING
                    state.hover_slot_id = None
                    state.lock_slot_id = None
                    state.lock_action_key = None
                    state.lock_frames = 0
                    state.baseline_z = tip[2]
                    state.baseline_tip = tip
                    state.last_tip = tip
                    state.last_forward = 0.0
                    state.last_velocity = 0.0
                    state.lateral_velocity = 0.0
                    state.camera_forward_disp = 0.0
                    state.camera_forward_velocity = 0.0
                    state.forward_velocity_samples.clear()
                    state.lateral_velocity_samples.clear()
                    state.camera_forward_velocity_samples.clear()
                    state.last_ts = now
                    continue

                if state.hover_slot_id == slot_id:
                    state.lock_frames += 1
                else:
                    state.hover_slot_id = slot_id
                    state.lock_slot_id = slot_id
                    state.lock_action_key = str(slot["key"])
                    state.lock_frames = 1
                    state.baseline_z = tip[2]
                    state.baseline_tip = tip
                    state.last_tip = tip
                    state.last_forward = 0.0
                    state.last_velocity = 0.0
                    state.lateral_velocity = 0.0
                    state.camera_forward_disp = 0.0
                    state.camera_forward_velocity = 0.0
                    state.forward_velocity_samples.clear()
                    state.lateral_velocity_samples.clear()
                    state.camera_forward_velocity_samples.clear()
                    if state.phase != FingerPhaseV2.PRESSED:
                        state.phase = FingerPhaseV2.TRACKING

                if state.baseline_z is None:
                    state.baseline_z = tip[2]
                if state.baseline_tip is None:
                    state.baseline_tip = tip
                if state.last_tip is None:
                    state.last_tip = tip

                if state.last_ts is None:
                    dt = 1e-3
                else:
                    dt = max(now - state.last_ts, 1e-3)

                tip_delta = self._vector_sub(tip, state.last_tip)
                forward_delta = self._vector_dot(tip_delta, axis)
                lateral_delta_vec = self._vector_sub(tip_delta, self._vector_scale(axis, forward_delta))
                lateral_velocity_raw = self._vector_norm(lateral_delta_vec) / dt

                baseline_delta = self._vector_sub(tip, state.baseline_tip)
                forward_disp = self._vector_dot(baseline_delta, axis)
                camera_forward_disp = state.baseline_z - tip[2]
                lateral_disp_vec = self._vector_sub(baseline_delta, self._vector_scale(axis, forward_disp))
                forward_velocity_raw = forward_delta / dt
                camera_forward_velocity_raw = (state.last_tip[2] - tip[2]) / dt
                forward_velocity = self._v2_smooth_velocity(state.forward_velocity_samples, forward_velocity_raw)
                lateral_velocity = self._v2_smooth_velocity(state.lateral_velocity_samples, lateral_velocity_raw)
                camera_forward_velocity = self._v2_smooth_velocity(
                    state.camera_forward_velocity_samples,
                    camera_forward_velocity_raw,
                )
                state.forward_disp = forward_disp
                state.last_velocity = forward_velocity
                state.last_forward = forward_disp
                state.last_tip = tip
                state.last_ts = now
                state.lateral_disp = self._vector_norm(lateral_disp_vec)
                state.lateral_velocity = lateral_velocity
                state.camera_forward_disp = camera_forward_disp
                state.camera_forward_velocity = camera_forward_velocity
                state.normalized_forward = forward_disp / max(press_disp_threshold, 1e-6)

                if state.phase in (FingerPhaseV2.TRACKING, FingerPhaseV2.ARMED, FingerPhaseV2.RELEASE_WAIT):
                    quiet = forward_disp <= (press_disp_threshold * 0.55)
                    moving_forward = forward_velocity > max(press_vel_threshold * 0.60, 0.02)
                    lateral_sweep = lateral_velocity > max(press_vel_threshold * 0.75, 0.03)
                    if quiet and not moving_forward and not lateral_sweep:
                        state.baseline_z = ((1.0 - baseline_alpha) * state.baseline_z) + (baseline_alpha * tip[2])
                        state.baseline_tip = (
                            ((1.0 - baseline_alpha) * state.baseline_tip[0]) + (baseline_alpha * tip[0]),
                            ((1.0 - baseline_alpha) * state.baseline_tip[1]) + (baseline_alpha * tip[1]),
                            ((1.0 - baseline_alpha) * state.baseline_tip[2]) + (baseline_alpha * tip[2]),
                        )

                if state.phase in (FingerPhaseV2.MISSING, FingerPhaseV2.TRACKING):
                    state.phase = FingerPhaseV2.TRACKING
                    if state.lock_frames >= self.v2_target_lock_frames:
                        state.phase = FingerPhaseV2.ARMED

                if state.phase == FingerPhaseV2.ARMED:
                    if state.lock_slot_id != slot_id:
                        state.phase = FingerPhaseV2.TRACKING
                        continue
                    should_press, press_reason = self._v2_simple_should_press(
                        state=state,
                        forward_disp=forward_disp,
                        forward_velocity=forward_velocity,
                        lateral_velocity=lateral_velocity,
                        camera_forward_disp=camera_forward_disp,
                        camera_forward_velocity=camera_forward_velocity,
                        press_disp_threshold=press_disp_threshold,
                        press_vel_threshold=press_vel_threshold,
                        now=now,
                        return_reason=True,
                    )
                    if self.debug_enabled:
                        print(
                            "[AIRTYPE-V2-CHECK] "
                            f"finger={finger_id} slot={state.lock_slot_id} phase={state.phase.value} "
                            f"v={forward_velocity:.4f} v_thr={press_vel_threshold:.4f} "
                            f"lat_v={lateral_velocity:.4f} f_disp={forward_disp:.4f} "
                            f"cam_v={camera_forward_velocity:.4f} cam_f={camera_forward_disp:.4f} "
                            f"pass={should_press} reason={press_reason}"
                        )
                    if should_press:
                        slot_for_press = self._slot_definition_by_id(state.lock_slot_id) or slot
                        if slot_for_press is not None:
                            confidence = self._clamp(
                                forward_disp / max(press_disp_threshold * 1.4, 1e-6),
                                0.0,
                                1.0,
                            )
                            self._v2_process_press(
                                state,
                                slot_for_press,
                                confidence,
                                now,
                                press_velocity=forward_velocity,
                            )
                            self._v2_last_global_press_ts = now
                            self._last_global_press_ts = now
                            action_executed = True
                    continue

                if state.phase == FingerPhaseV2.PRESSED:
                    action_executed = self._maybe_repeat_v2(state, now) or action_executed
                    if self._v2_should_release(
                        forward_disp=forward_disp,
                        forward_velocity=forward_velocity,
                        release_disp_threshold=release_disp_threshold,
                    ):
                        self._v2_process_release(state)
                    continue

                if state.phase == FingerPhaseV2.RELEASE_WAIT:
                    stable = (
                        forward_disp <= release_disp_threshold
                        and abs(forward_velocity) <= max(press_vel_threshold * 0.55, 0.05)
                    )
                    if stable:
                        state.rearm_frames += 1
                    else:
                        state.rearm_frames = 0

                    if state.rearm_frames >= max(1, self.v2_rearm_frames):
                        state.phase = FingerPhaseV2.TRACKING
                        state.active_slot_id = None
                        state.active_action_key = None
                        state.press_confidence = 0.0
                        state.baseline_z = tip[2]
                        state.baseline_tip = tip
                        state.last_forward = 0.0
                        state.forward_disp = 0.0
                        state.last_velocity = 0.0
                        state.lateral_velocity = 0.0
                        state.camera_forward_disp = 0.0
                        state.camera_forward_velocity = 0.0
                        state.forward_velocity_samples.clear()
                        state.lateral_velocity_samples.clear()
                        state.camera_forward_velocity_samples.clear()
                    continue

        for finger_id, state in list(self._state_by_finger_v2.items()):
            if finger_id in seen_fingers:
                continue
            if state.phase == FingerPhaseV2.PRESSED:
                self._v2_process_release(state)
            self._reset_v2_runtime(state)

        self._hovered_slots = hovered_slots
        self._status = "Keyboard Ready (Forward Tap)"

        if self.debug_enabled and (now - self._last_debug_log_ts) >= self._debug_log_interval_sec:
            li = self._get_state_v2("left_index")
            ri = self._get_state_v2("right_index")
            pointer_id = "left_index" if abs(li.last_velocity) >= abs(ri.last_velocity) else "right_index"
            pointer_state = li if pointer_id == "left_index" else ri
            print(
                "[AIRTYPE-V2-SIMPLE] "
                f"press_vel_thr={press_vel_threshold:.4f} "
                f"pointer={pointer_id}(v={pointer_state.last_velocity:.4f},"
                f"lat_v={pointer_state.lateral_velocity:.4f},"
                f"cam_v={pointer_state.camera_forward_velocity:.4f},"
                f"slot={pointer_state.lock_slot_id},phase={pointer_state.phase.value}) "
                f"L(v={li.last_velocity:.4f},lat_v={li.lateral_velocity:.4f}) "
                f"R(v={ri.last_velocity:.4f},lat_v={ri.lateral_velocity:.4f}) "
                f"last={self._last_event}"
            )
            self._last_debug_log_ts = now
        return action_executed

    def _update_v2(self, hands_data: HandsData, frame_capture_ts_ns=None):
        action_executed = False

        camera_hands = self._get_hands_by_side(hands_data.camera)
        candidate_frames = {
            "left": self._compute_hand_frame("left", camera_hands.get("left")),
            "right": self._compute_hand_frame("right", camera_hands.get("right")),
        }

        # Keep current keyboard placement behavior unchanged.
        recenter = self._paused or (not self._v2_calibrated)
        self._update_active_frames(candidate_frames, recenter=recenter)

        active_frames = self._spread_overlay_frames(self._active_frames, hands_data)
        if active_frames.get("left") is None and active_frames.get("right") is None:
            active_frames = self._fallback_overlay_frames()

        self._set_overlay_keys(self._build_overlay_keys(active_frames))
        self._update_drag_bounds(active_frames)
        unified_frame = self._resolve_unified_frame(active_frames) if not self.keyboard_split_layout else None

        if self.require_both_hands and not self._both_hands_present(hands_data):
            self._pause("Typing Paused: both hands required")
            return False

        if self._paused:
            self._resume_if_stable(hands_data)
            if self._paused:
                return False

        if self.require_both_hands and (
            candidate_frames["left"] is None or candidate_frames["right"] is None
        ):
            self._pause("Typing Paused: both hands required")
            return False

        now = self._timestamp_seconds(frame_capture_ts_ns=frame_capture_ts_ns)
        self._v2_last_now = now
        hovered_slots = set()
        self._v2_start_calibration_if_needed(now)

        present_sides = {
            side
            for side in ("left", "right")
            if camera_hands.get(side) is not None and camera_hands.get(side).exists
        }
        for side in ("left", "right"):
            if side not in present_sides:
                self._v2_reset_missing_side(side)

        # Collect calibration samples from currently tracked fingers.
        if not self._v2_calibrated:
            for side in ("left", "right"):
                frame = unified_frame if unified_frame is not None else active_frames.get(side)
                camera_hand = camera_hands.get(side)
                if frame is None or camera_hand is None or not camera_hand.exists:
                    continue

                axis = self._palm_axis_toward_camera(camera_hand)
                for finger_name in self._finger_names_v2():
                    finger_id = f"{side}_{finger_name}"
                    tip = self._get_tip(camera_hand, finger_name)
                    if tip is None:
                        continue

                    slot = self._map_tip_to_slot(side, tip, frame)
                    if slot is not None:
                        hovered_slots.add(str(slot["id"]))
                    self._v2_collect_calibration_sample(finger_id, tip, axis, now)

            if not self._v2_try_finish_calibration(camera_hands, now):
                progress = int(round(self._v2_calibration_progress(now) * 100.0))
                self._status = f"Keyboard Calibrating ({progress}%) - hold steady"
                self._hovered_slots = hovered_slots
                self._last_confidence = 0.0
                return False

        for side in ("left", "right"):
            frame = unified_frame if unified_frame is not None else active_frames.get(side)
            camera_hand = camera_hands.get(side)
            if frame is None or camera_hand is None or not camera_hand.exists:
                continue

            axis = self._palm_axis_toward_camera(camera_hand)
            for finger_name in self._finger_names_v2():
                finger_id = f"{side}_{finger_name}"
                state = self._get_state_v2(finger_id)
                profile = self._get_profile_v2(finger_id)

                tip = self._get_tip(camera_hand, finger_name)
                if tip is None:
                    if state.phase == FingerPhaseV2.PRESSED:
                        self._v2_process_release(state)
                    self._reset_v2_runtime(state)
                    continue

                slot = self._map_tip_to_slot(side, tip, frame)
                slot_id = str(slot["id"]) if slot is not None else None
                if slot_id is not None:
                    hovered_slots.add(slot_id)

                if not profile.calibrated or profile.neutral_tip is None:
                    state.phase = FingerPhaseV2.TRACKING
                    state.hover_slot_id = slot_id
                    continue

                self._v2_update_finger_metrics(state, profile, tip, axis, now)
                press_disp_threshold = self._v2_press_displacement_threshold(profile)
                press_vel_threshold = self._v2_press_velocity_threshold(profile)
                release_disp_threshold = self._v2_release_displacement_threshold(press_disp_threshold, profile)
                lateral_limit = self._v2_lateral_limit(state.lock_slot_id or slot_id, profile)
                state.normalized_forward = state.forward_disp / max(press_disp_threshold, 1e-6)

                if state.phase in (FingerPhaseV2.MISSING, FingerPhaseV2.TRACKING):
                    state.phase = FingerPhaseV2.TRACKING
                    if slot_id is None:
                        state.hover_slot_id = None
                        state.lock_slot_id = None
                        state.lock_action_key = None
                        state.lock_frames = 0
                        continue

                    if state.hover_slot_id == slot_id:
                        state.lock_frames += 1
                    else:
                        state.hover_slot_id = slot_id
                        state.lock_frames = 1

                    if state.lock_frames >= self.v2_target_lock_frames:
                        state.phase = FingerPhaseV2.ARMED
                        state.lock_slot_id = slot_id
                        state.lock_action_key = str(slot["key"])
                    continue

                if state.phase == FingerPhaseV2.ARMED:
                    if state.lock_slot_id is None or state.lock_action_key is None:
                        state.phase = FingerPhaseV2.TRACKING
                        state.lock_frames = 0
                        continue

                    if not self._v2_tip_within_lock_bounds(tip, state.lock_slot_id):
                        state.phase = FingerPhaseV2.TRACKING
                        state.lock_slot_id = None
                        state.lock_action_key = None
                        state.lock_frames = 0
                        continue

                    self._v2_maybe_lock_forward_polarity(
                        profile=profile,
                        state=state,
                        press_disp_threshold=press_disp_threshold,
                        press_vel_threshold=press_vel_threshold,
                        lateral_limit=lateral_limit,
                    )

                    if self._v2_should_press(
                        state=state,
                        forward_disp=state.forward_disp,
                        forward_velocity=state.last_velocity,
                        lateral_disp=state.lateral_disp,
                        press_disp_threshold=press_disp_threshold,
                        press_vel_threshold=press_vel_threshold,
                        lateral_limit=lateral_limit,
                        now=now,
                    ):
                        slot_for_press = slot
                        if slot_for_press is None or str(slot_for_press["id"]) != state.lock_slot_id:
                            slot_for_press = self._slot_definition_by_id(state.lock_slot_id)
                        if slot_for_press is not None:
                            forward_conf = state.forward_disp / max(press_disp_threshold, 1e-6)
                            vel_conf = state.last_velocity / max(press_vel_threshold, 1e-6)
                            confidence = self._clamp(0.5 * (forward_conf + vel_conf), 0.0, 1.0)
                            self._v2_process_press(
                                state,
                                slot_for_press,
                                confidence,
                                now,
                                press_velocity=state.last_velocity,
                            )
                            action_executed = True
                            self._last_global_press_ts = now
                    continue

                if state.phase == FingerPhaseV2.PRESSED:
                    if (
                        state.active_action_key in MODIFIER_KEYS
                        and not state.modifier_held
                        and (now - state.last_press_ts) >= (self.v2_modifier_hold_ms / 1000.0)
                        and state.forward_disp >= (press_disp_threshold * 0.90)
                    ):
                        self._key_down(state.active_action_key)
                        state.modifier_held = True
                        action_executed = True

                    action_executed = self._maybe_repeat_v2(state, now) or action_executed
                    if self._v2_should_release(
                        forward_disp=state.forward_disp,
                        forward_velocity=state.last_velocity,
                        release_disp_threshold=release_disp_threshold,
                    ):
                        self._v2_process_release(state)
                    continue

                if state.phase == FingerPhaseV2.RELEASE_WAIT:
                    stable_rearm = (
                        state.forward_disp <= release_disp_threshold
                        and abs(state.last_velocity) <= max(press_vel_threshold * 0.55, 0.04)
                    )
                    if stable_rearm:
                        state.rearm_frames += 1
                    else:
                        state.rearm_frames = 0

                    if state.rearm_frames >= self.v2_rearm_frames:
                        state.phase = FingerPhaseV2.TRACKING
                        state.lock_slot_id = None
                        state.lock_action_key = None
                        state.lock_frames = 0
                        state.active_slot_id = None
                        state.active_action_key = None
                        state.press_confidence = 0.0
                        if slot_id is not None:
                            state.hover_slot_id = slot_id
                            state.lock_frames = 1
                    continue

                # Safety fallback for unknown phase values.
                state.phase = FingerPhaseV2.TRACKING

        self._hovered_slots = hovered_slots
        self._status = "Keyboard Ready (Forward Poke)"

        if self.debug_enabled and (now - self._last_debug_log_ts) >= self._debug_log_interval_sec:
            li = self._get_state_v2("left_index")
            ri = self._get_state_v2("right_index")
            print(
                "[AIRTYPE-V2] "
                f"status='{self._status}' "
                f"L(phase={li.phase.value},slot={li.lock_slot_id},f={li.forward_disp:.4f},v={li.last_velocity:.3f}) "
                f"R(phase={ri.phase.value},slot={ri.lock_slot_id},f={ri.forward_disp:.4f},v={ri.last_velocity:.3f}) "
                f"last={self._last_event}"
            )
            self._last_debug_log_ts = now

        return action_executed

    def update(self, hands_data: HandsData, frame_capture_ts_ns=None):
        if self.keyboard_v2_enabled:
            if self.v2_simple_forward_tap:
                return self._update_v2_simple(hands_data, frame_capture_ts_ns=frame_capture_ts_ns)
            return self._update_v2(hands_data, frame_capture_ts_ns=frame_capture_ts_ns)

        action_executed = False

        camera_hands = self._get_hands_by_side(hands_data.camera)
        wrist_hands = self._get_hands_by_side(hands_data.wrist)

        candidate_frames = {
            "left": self._compute_hand_frame("left", camera_hands.get("left")),
            "right": self._compute_hand_frame("right", camera_hands.get("right")),
        }

        # While calibrating we recenter keyboards around current hands; after that,
        # keep keyboards fixed unless hands leave the surrounding deadzone bounds.
        self._update_active_frames(candidate_frames, recenter=self._paused)

        active_frames = self._spread_overlay_frames(self._active_frames, hands_data)
        if active_frames.get("left") is None and active_frames.get("right") is None:
            active_frames = self._fallback_overlay_frames()

        self._set_overlay_keys(self._build_overlay_keys(active_frames))
        self._update_drag_bounds(active_frames)
        unified_frame = self._resolve_unified_frame(active_frames) if not self.keyboard_split_layout else None

        if self.require_both_hands and not self._both_hands_present(hands_data):
            self._pause("Typing Paused: both hands required")
            return False

        if self._paused:
            self._resume_if_stable(hands_data)
            if self._paused:
                return False

        if self.require_both_hands and (
            candidate_frames["left"] is None or candidate_frames["right"] is None
        ):
            self._pause("Typing Paused: both hands required")
            return False

        hovered_slots = set()
        now = self._timestamp_seconds(frame_capture_ts_ns=frame_capture_ts_ns)
        refractory_seconds = self.min_refractory_ms / 1000.0
        global_interval_seconds = self.min_global_key_interval_ms / 1000.0

        for side in ("left", "right"):
            frame = unified_frame if unified_frame is not None else active_frames.get(side)
            camera_hand = camera_hands.get(side)
            wrist_hand = wrist_hands.get(side)
            if frame is None or camera_hand is None or wrist_hand is None:
                continue

            for finger_name in self._finger_names():
                finger_id = f"{side}_{finger_name}"
                state = self._get_state(finger_id)

                tip = self._get_tip(camera_hand, finger_name)
                bend, radius = self._get_finger_bend_radius(wrist_hand, finger_name)

                if tip is None or bend is None or radius is None:
                    if state.phase == FingerPhase.PRESSED:
                        self._process_release(finger_id)
                    state.hover_slot_id = None
                    state.hover_frames = 0
                    state.hover_baseline_bend = None
                    state.hover_baseline_radius = None
                    state.hover_baseline_z = None
                    state.last_z = None
                    state.last_ts = None
                    continue

                slot = self._map_tip_to_slot(side, tip, frame)
                if slot is not None:
                    hovered_slots.add(str(slot["id"]))

                if slot is not None and state.hover_slot_id == str(slot["id"]):
                    state.hover_frames += 1
                elif slot is not None:
                    state.hover_slot_id = str(slot["id"])
                    state.hover_frames = 1
                    state.hover_baseline_bend = bend
                    state.hover_baseline_radius = radius
                    state.hover_baseline_z = tip[2]
                else:
                    state.hover_slot_id = None
                    state.hover_frames = 0
                    state.hover_baseline_bend = None
                    state.hover_baseline_radius = None
                    state.hover_baseline_z = None

                if (
                    slot is not None
                    and state.phase == FingerPhase.HOVER
                    and state.hover_frames < self.press_hover_frames
                ):
                    if state.hover_baseline_bend is None:
                        state.hover_baseline_bend = bend
                    else:
                        a = self.hover_baseline_alpha
                        state.hover_baseline_bend = (1.0 - a) * state.hover_baseline_bend + a * bend

                    if state.hover_baseline_radius is None:
                        state.hover_baseline_radius = radius
                    else:
                        a = self.hover_baseline_alpha
                        state.hover_baseline_radius = (1.0 - a) * state.hover_baseline_radius + a * radius
                    if state.hover_baseline_z is None:
                        state.hover_baseline_z = tip[2]
                    else:
                        a = self.hover_baseline_alpha
                        state.hover_baseline_z = (1.0 - a) * state.hover_baseline_z + a * tip[2]

                baseline_bend = state.hover_baseline_bend if state.hover_baseline_bend is not None else bend
                baseline_radius = state.hover_baseline_radius if state.hover_baseline_radius is not None else radius
                baseline_z = state.hover_baseline_z if state.hover_baseline_z is not None else tip[2]

                bend_delta = max(0.0, bend - baseline_bend)
                radius_drop = max(0.0, baseline_radius - radius)
                depth_delta = max(0.0, baseline_z - tip[2])

                z_velocity_toward_camera = 0.0
                if state.last_z is not None and state.last_ts is not None:
                    dt = max(now - state.last_ts, 1e-3)
                    z_velocity_toward_camera = (state.last_z - tip[2]) / dt

                press_signal = (
                    (
                        (bend >= self.press_bend_threshold or bend_delta >= self.press_bend_delta_threshold)
                        and radius_drop >= self.press_radius_drop_threshold
                    )
                    or (bend_delta >= (self.press_bend_delta_threshold * 1.7))
                    or (
                        depth_delta >= self.press_depth_threshold
                        and z_velocity_toward_camera >= self.press_depth_velocity_threshold
                    )
                )

                if state.phase == FingerPhase.HOVER:
                    if (
                        slot is not None
                        and state.hover_frames >= self.press_hover_frames
                        and press_signal
                        and (now - state.last_press_ts) >= refractory_seconds
                        and (now - self._last_global_press_ts) >= global_interval_seconds
                    ):
                        bend_conf = max(bend / max(self.press_bend_threshold, 1e-6), bend_delta / max(self.press_bend_delta_threshold, 1e-6))
                        radius_conf = radius_drop / max(self.press_radius_drop_threshold, 1e-6)
                        confidence = max(0.0, min(1.0, 0.5 * (bend_conf + radius_conf)))
                        self._process_press(finger_id, slot, confidence, now=now)
                        self._last_global_press_ts = now
                        action_executed = True

                elif state.phase == FingerPhase.PRESSED:
                    action_executed = self._maybe_repeat(state, now=now) or action_executed

                    release_by_slot = slot is None or str(slot["id"]) != state.active_slot_id
                    release_by_depth = depth_delta <= self.release_depth_threshold
                    if state.active_action_key in MODIFIER_KEYS:
                        release_signal = (
                            bend <= self.release_bend_threshold
                            and radius_drop <= self.release_radius_drop_threshold
                            and release_by_depth
                        )
                    else:
                        release_signal = (
                            bend <= self.release_bend_threshold
                            or radius_drop <= self.release_radius_drop_threshold
                            or release_by_depth
                        )

                    if release_by_slot or release_signal:
                        self._process_release(finger_id)

                state.last_bend = bend
                state.last_radius = radius
                state.last_z = tip[2]
                state.last_ts = now

        self._hovered_slots = hovered_slots

        if self.debug_enabled and (now - self._last_debug_log_ts) >= self._debug_log_interval_sec:
            li = self._get_state("left_index")
            ri = self._get_state("right_index")
            print(
                "[AIRTYPE] "
                f"status='{self._status}' "
                f"L(phase={li.phase.value},slot={li.hover_slot_id},bend={li.last_bend},hover={li.hover_frames}) "
                f"R(phase={ri.phase.value},slot={ri.hover_slot_id},bend={ri.last_bend},hover={ri.hover_frames}) "
                f"last={self._last_event}"
            )
            self._last_debug_log_ts = now

        self._status = "Keyboard Ready (Wrist Relative)"
        return action_executed

    def detect_gesture(self, hands_data: HandsData):
        # Not used directly; update() handles full flow.
        return True, hands_data

    def execute_action(self, data):
        # Not used directly; update() handles full flow.
        return

    def reset(self):
        self.action.release_all_keys()
        self._held_modifiers.clear()
        self._state_by_finger.clear()
        self._state_by_finger_v2.clear()
        self._profile_by_finger_v2.clear()
        self._hovered_slots.clear()
        self._overlay_keys = []
        self._overlay_by_id = {}
        self._active_frames = {"left": None, "right": None}
        self._drag_bounds_by_side = {}
        self._anchor_avg = {"left": None, "right": None}
        self._size_avg = {"left": None, "right": None}
        self._paused = True
        self._resume_counter = 0
        self._status = "Calibrating..."
        self._last_event = ""
        self._last_confidence = 0.0
        self._last_global_press_ts = 0.0
        self._single_hand_side_hint = None
        self._v2_calibrated = False
        self._v2_calibration_started_ts = None
        self._v2_last_global_press_ts = 0.0
        self._v2_last_now = 0.0

    @property
    def is_active(self):
        return not self._paused

    @property
    def current_state(self):
        return self._status

    def _v2_overlay_diagnostics(self):
        finger_rows = []
        for finger_id in sorted(self._state_by_finger_v2.keys()):
            state = self._state_by_finger_v2[finger_id]
            profile = self._profile_by_finger_v2.get(finger_id)
            finger_rows.append(
                {
                    "finger_id": finger_id,
                    "phase": state.phase.value,
                    "locked_key": state.lock_slot_id,
                    "forward_disp": state.forward_disp,
                    "lateral_disp": state.lateral_disp,
                    "normalized_forward": state.normalized_forward,
                    "press_confidence": state.press_confidence,
                    "calibrated": bool(profile.calibrated) if profile is not None else False,
                    "forward_polarity": profile.forward_polarity if profile is not None else 1.0,
                    "forward_polarity_locked": bool(profile.forward_polarity_locked) if profile is not None else False,
                }
            )

        now = self._v2_last_now if self._v2_last_now > 0.0 else time.time()
        if self.require_both_hands:
            required_ids = [
                f"{side}_{finger_name}"
                for side in ("left", "right")
                for finger_name in self._finger_names_v2()
            ]
        else:
            required_ids = list(self._profile_by_finger_v2.keys())
        profile_calibrated = sum(
            1
            for finger_id in required_ids
            if self._profile_by_finger_v2.get(finger_id) is not None
            and self._profile_by_finger_v2[finger_id].calibrated
        )
        calibration_payload = {
            "active": not self._v2_calibrated,
            "progress": self._v2_calibration_progress(now),
            "calibration_ms": self.v2_calibration_ms,
            "ready_fingers": profile_calibrated,
            "required_fingers": len(required_ids),
        }
        return {"fingers": finger_rows, "calibration": calibration_payload}

    def get_overlay_data(self):
        if self.keyboard_v2_enabled:
            pressed_slots = {
                s.active_slot_id
                for s in self._state_by_finger_v2.values()
                if s.phase == FingerPhaseV2.PRESSED and s.active_slot_id
            }
            diagnostics = self._v2_overlay_diagnostics()
        else:
            pressed_slots = {
                s.active_slot_id
                for s in self._state_by_finger.values()
                if s.phase == FingerPhase.PRESSED and s.active_slot_id
            }
            diagnostics = {"fingers": [], "calibration": {"active": False, "progress": 1.0}}
        drag_bounds = []
        for side, bound in self._drag_bounds_by_side.items():
            if bound is None:
                continue
            drag_bounds.append(
                {
                    "side": side,
                    "x": bound.left,
                    "y": bound.top,
                    "w": bound.width,
                    "h": bound.height,
                }
            )

        return {
            "enabled": True,
            "calibrated": (not self._paused) and (self._v2_calibrated if self.keyboard_v2_enabled else True),
            "status": self._status,
            "keys": self._overlay_keys,
            "drag_bounds": drag_bounds,
            "hovered_keys": list(self._hovered_slots),
            "pressed_keys": list(pressed_slots),
            "last_event": self._last_event,
            "press_confidence": self._last_confidence,
            "finger_diagnostics": diagnostics["fingers"],
            "calibration": diagnostics["calibration"],
        }
