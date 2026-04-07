import math
import platform
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.HandsData import HandsData
from backend.gestures.FlickDetector import FlickDetector
from backend.gestures.GestureRecognizer import GestureRecognizer
from backend.gestures.GestureUtils import (
    are_fingers_pinched,
    get_finger_angle,
    get_finger_extension,
    get_hand_openness,
    get_pinch_distance,
)
from backend.gestures.keyboard_mode.DevOverlayKeyboardSurface import DevOverlayKeyboardSurface
from backend.gestures.keyboard_mode.KeyboardLayoutHelper import KeyboardLayoutHelper
from backend.gestures.keyboard_mode.KeyboardThemes import KeyboardThemeRegistry
from backend.gestures.keyboard_mode.KeyboardSurfaceBase import HandFrame, KeyboardSurfaceBase
from backend.gestures.keyboard_mode.ProdWindowKeyboardSurface import ProdWindowKeyboardSurface
from backend.gestures.keyboard_mode.SwipeDecoder import SwipeDecoder


@dataclass
class SwipeWordRecord:
    selected_word: str
    candidates: List[str]
    emitted_text: str
    confidence: float


class AirTypingGesture(GestureRecognizer):
    """
    Keyboard overlay gesture for keyboard mode.

    This gesture:
    - draws and moves keyboard overlays
    - highlights hovered keys
    - supports right-hand swipe typing with click-style pinch clutch
    """
    _MODIFIER_SLOT_TO_FAMILY = KeyboardLayoutHelper.MODIFIER_SLOT_TO_FAMILY
    _MODIFIER_FAMILY_TO_KEY = KeyboardLayoutHelper.MODIFIER_FAMILY_TO_KEY
    _MODIFIER_FAMILY_TO_SLOTS = KeyboardLayoutHelper.MODIFIER_FAMILY_TO_SLOTS
    _MODIFIER_PRESS_ORDER = KeyboardLayoutHelper.MODIFIER_PRESS_ORDER
    _FN_KEY_TO_FUNCTION = KeyboardLayoutHelper.FN_KEY_TO_FUNCTION
    _SUGGESTION_CHIP_COUNT = KeyboardLayoutHelper.SUGGESTION_CHIP_COUNT
    _SWIPE_HISTORY_LIMIT = 10
    _DELETE_FLICK_MIN_DISPLACEMENT = 0.085
    _DELETE_FLICK_MIN_DOMINANCE_RATIO = 1.75
    _DELETE_FLICK_MAX_HORIZONTAL_DRIFT = 0.07
    _DELETE_FLICK_MIN_SMOOTHNESS = 0.86
    _FLICK_REARM_STABLE_FRAMES = 2
    _FLICK_REARM_MAX_STEP = 0.018
    _FLICK_REARM_ESCAPE_DISTANCE = 0.045
    _EXIT_FIST_MAX_THUMB_EXTENSION_RATIO = 0.98
    _DEFAULT_REPLACE_FLICK_COOLDOWN_SECONDS = 0.75

    def __init__(
        self,
        action,
        config,
        priority=15,
        *,
        ui_mode: str = "dev",
        screen_width: int = 1920,
        screen_height: int = 1080,
        keyboard_surface: Optional[KeyboardSurfaceBase] = None,
    ):
        super().__init__(action, priority=priority)
        self.config = config
        self.ui_mode = str(ui_mode)
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)
        os_name = platform.system()
        if os_name == "Darwin":
            self._meta_key_label = "Cmd"
        elif os_name == "Linux":
            self._meta_key_label = "Super"
        else:
            self._meta_key_label = "Win"

        # constants for unified swipe keyboard mode.
        self.require_both_hands = False
        self.pause_on_hand_loss = True
        self.resume_stability_frames = 4
        self.use_thumb_fingers = False
        self.active_fingers = ["index"]

        self.keyboard_fixed_center_mode = True
        self.flip_x_for_mapping = bool(
            self.config.get(
                "keyboard_flip_x_for_mapping",
                self.config.get("preview_flip_horizontal", True),
            )
        )
        self.pinch_threshold = float(self.config.get("pinch_threshold", 0.15))

        # Swipe typing configuration
        self.keyboard_swipe_enabled = True
        self.keyboard_swipe_min_points = int(self.config.get("keyboard_swipe_min_points", 4))
        self.keyboard_swipe_min_unique_keys = int(self.config.get("keyboard_swipe_min_unique_keys", 3))
        self.keyboard_swipe_decode_top_k = 8
        self.keyboard_swipe_release_pinch_threshold = float(
            self.config.get("keyboard_swipe_release_pinch_threshold", 0.50)
        )
        if self.keyboard_swipe_release_pinch_threshold < self.pinch_threshold:
            self.keyboard_swipe_release_pinch_threshold = self.pinch_threshold
        self.keyboard_swipe_release_pending_frames = int(
            self.config.get("keyboard_swipe_release_pending_frames", 2)
        )
        if self.keyboard_swipe_release_pending_frames < 1:
            self.keyboard_swipe_release_pending_frames = 1
        self.keyboard_swipe_tracking_grace_frames = int(
            self.config.get("keyboard_swipe_tracking_grace_frames", 8)
        )
        if self.keyboard_swipe_tracking_grace_frames < 0:
            self.keyboard_swipe_tracking_grace_frames = 0
        self.keyboard_swipe_auto_space = True
        self.replace_flick_cooldown_seconds = max(
            0.0,
            float(
                self.config.get(
                    "keyboard_replace_flick_cooldown_seconds",
                    self._DEFAULT_REPLACE_FLICK_COOLDOWN_SECONDS,
                )
            ),
        )
        self._swipe_point_min_distance = 0.0035
        self._swipe_point_min_distance_sq = self._swipe_point_min_distance * self._swipe_point_min_distance

        self._paused = True
        self._status = "Keyboard Initializing..."
        self._resume_counter = 0

        self._last_event = ""
        self._last_confidence = 0.0

        self._overlay_keys: List[Dict[str, object]] = []
        self._overlay_by_id: Dict[str, Dict[str, object]] = {}
        self._active_frames: Dict[str, Optional[HandFrame]] = {"left": None, "right": None}
        self._drag_bounds_by_side: Dict[str, HandFrame] = {}
        self._anchor_avg: Dict[str, Optional[Tuple[float, float]]] = {"left": None, "right": None}
        self._size_avg: Dict[str, Optional[Tuple[float, float]]] = {"left": None, "right": None}
        self._surface_extra_overlay: Dict[str, object] = {}
        self._hovered_slots = set()
        self._right_index_hover_point: Optional[Tuple[float, float]] = None
        self._right_frame_for_swipe: Optional[HandFrame] = None

        self._swipe_active = False
        self._swipe_points: List[Tuple[float, float]] = []
        self._swipe_trace_slots: List[str] = []
        self._swipe_trace: List[str] = []
        self._swipe_candidates: List[str] = []
        self._swipe_best = ""
        self._swipe_confidence = 0.0
        self._swipe_release_counter = 0
        self._swipe_lost_frames = 0
        self._special_key_pinch_latched = False
        self._last_pinch_value: Optional[float] = None
        self._exit_fist_ready = False
        self._swipe_word_history: List[SwipeWordRecord] = []
        self._suggestion_words: List[str] = []
        self._suggestion_chips: List[Dict[str, object]] = []
        self._hovered_suggestion_idx: Optional[int] = None
        self._active_modifiers = set()
        self._caps_lock_active = False
        self._overlay_bounds: Optional[Tuple[float, float, float, float]] = None

        self._keyboard_layout_id = str(self.config.get("keyboard_layout", "qwerty") or "qwerty").strip().lower()
        self._keyboard_theme_id = KeyboardThemeRegistry.get(
            str(self.config.get("keyboard_theme", "dark") or "dark")
        ).theme_id
        self._rows_unified = KeyboardLayoutHelper.build_unified_rows(
            self._meta_key_label,
            layout_id=self._keyboard_layout_id,
        )
        self._slot_to_key = KeyboardLayoutHelper.build_slot_key_map(self._rows_unified)
        self._shift_label_by_slot = KeyboardLayoutHelper.build_slot_shift_label_map(self._rows_unified)
        self._swipe_token_by_slot = KeyboardLayoutHelper.build_slot_swipe_token_map(self._rows_unified)

        if keyboard_surface is not None:
            self._surface = keyboard_surface
        elif self.ui_mode == "prod":
            self._surface = ProdWindowKeyboardSurface(
                self.config,
                flip_x_for_mapping=self.flip_x_for_mapping,
                screen_width=self.screen_width,
                screen_height=self.screen_height,
            )
        else:
            self._surface = DevOverlayKeyboardSurface(
                self.config,
                flip_x_for_mapping=self.flip_x_for_mapping,
                screen_width=self.screen_width,
                screen_height=self.screen_height,
            )

        lexicon_path = Path(__file__).resolve().parent / "data" / "swipe-words.txt"
        self._swipe_decoder = SwipeDecoder(lexicon_path, max_words=None)
        self._flick_window_active = False
        self._flick_right_missing = False
        self._flick_rearm_pending = False
        self._flick_rearm_escape_direction: Optional[str] = None
        self._flick_rearm_origin_point: Optional[Tuple[float, float]] = None
        self._flick_rearm_last_point: Optional[Tuple[float, float]] = None
        self._flick_rearm_stable_frames = 0
        self._flick_rearm_max_step_sq = self._FLICK_REARM_MAX_STEP * self._FLICK_REARM_MAX_STEP
        self._flick_rearm_escape_distance_sq = self._FLICK_REARM_ESCAPE_DISTANCE * self._FLICK_REARM_ESCAPE_DISTANCE
        self._replace_flick_cooldown_until = 0.0
        flick_min_displacement = float(self.config.get("keyboard_flick_min_displacement", 0.075))
        flick_min_speed = float(self.config.get("keyboard_flick_min_speed", 0.25))
        flick_dominance_ratio = float(self.config.get("keyboard_flick_dominance_ratio", 1.2))
        self._flick_detector = FlickDetector(
            allowed_directions=("left", "right", "up"),
            min_displacement=flick_min_displacement,
            min_speed=flick_min_speed,
            dominance_ratio=flick_dominance_ratio,
        )
        self._delete_flick_detector = FlickDetector(
            allowed_directions=("down",),
            min_displacement=max(flick_min_displacement, self._DELETE_FLICK_MIN_DISPLACEMENT),
            min_speed=flick_min_speed,
            dominance_ratio=max(flick_dominance_ratio, self._DELETE_FLICK_MIN_DOMINANCE_RATIO),
        )

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
        return math.sqrt((dx * dx) + (dy * dy) + (dz * dz))

    @staticmethod
    def _clamp(value: float, min_value: float, max_value: float) -> float:
        return max(min_value, min(max_value, value))

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

    def _get_camera_hands(self, coord_space) -> Dict[str, object]:
        return {
            "left": coord_space.left if coord_space.has_left else None,
            "right": coord_space.right if coord_space.has_right else None,
        }

    def _get_tip(self, hand, finger_name: str) -> Optional[Tuple[float, float, float]]:
        if hand is None or not hand.exists:
            return None
        finger = getattr(hand, finger_name, None)
        if finger is None or finger.tip is None:
            return None
        return self._normalized_point(finger.tip)

    def _slot_from_uv(self, side: str, u: float, v: float) -> Optional[Dict[str, object]]:
        if u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0:
            return None

        rows = self._rows_unified
        if not rows:
            return None

        row_idx = min(len(rows) - 1, max(0, int(v * len(rows))))
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

    def _set_overlay_keys(self, key_rects: List[Dict[str, object]]):
        self._overlay_keys = key_rects
        self._overlay_by_id = {str(key["id"]): key for key in key_rects}
        if key_rects:
            min_x = min(float(key["x"]) for key in key_rects)
            min_y = min(float(key["y"]) for key in key_rects)
            max_x = max(float(key["x"]) + float(key["w"]) for key in key_rects)
            max_y = max(float(key["y"]) + float(key["h"]) for key in key_rects)
            self._overlay_bounds = (min_x, min_y, max_x, max_y)
        else:
            self._overlay_bounds = None
        self._layout_suggestion_chips()

    def _layout_suggestion_chips(self):
        self._suggestion_chips = []
        if not self._suggestion_words or self._overlay_bounds is None:
            return

        min_x, min_y, max_x, max_y = self._overlay_bounds
        keyboard_w = max(0.05, max_x - min_x)
        keyboard_h = max(0.05, max_y - min_y)
        chip_gap = keyboard_w * 0.012
        chip_count = self._SUGGESTION_CHIP_COUNT
        chip_h = self._clamp(keyboard_h * 0.16, keyboard_h * 0.10, keyboard_h * 0.22)
        chip_y = max(0.004, min_y - chip_h - (keyboard_h * 0.03))
        total_gap = chip_gap * (chip_count - 1)
        chip_w = max(0.05, (keyboard_w - total_gap) / chip_count)

        for idx in range(chip_count):
            label = self._suggestion_words[idx] if idx < len(self._suggestion_words) else ""
            chip_x = min_x + (idx * (chip_w + chip_gap))
            self._suggestion_chips.append(
                {
                    "id": f"suggestion_{idx}",
                    "index": idx,
                    "text": label,
                    "x": chip_x,
                    "y": chip_y,
                    "w": chip_w,
                    "h": chip_h,
                }
            )

    @staticmethod
    def _point_in_rect(point: Tuple[float, float], rect: Dict[str, object]) -> bool:
        px, py = point
        x = float(rect["x"])
        y = float(rect["y"])
        w = float(rect["w"])
        h = float(rect["h"])
        return (x <= px <= (x + w)) and (y <= py <= (y + h))

    def _suggestion_index_at_point(self, point: Tuple[float, float]) -> Optional[int]:
        for chip in self._suggestion_chips:
            if not chip.get("text"):
                continue
            if self._point_in_rect(point, chip):
                return int(chip["index"])
        return None

    def _current_right_tip(self, hands_data: HandsData) -> Optional[Tuple[float, float, float]]:
        right_hand = hands_data.camera.right if hands_data.camera.has_right else None
        if right_hand is None or not right_hand.exists:
            return None
        return self._get_tip(right_hand, "index")

    def _current_right_suggestion_index(self, hands_data: HandsData) -> Optional[int]:
        tip = self._current_right_tip(hands_data)
        if tip is None:
            return None
        return self._suggestion_index_at_point((tip[0], tip[1]))

    @staticmethod
    def _unique_words(words: List[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        for word in words:
            if not word:
                continue
            w = str(word).strip().lower()
            if not w or w in seen:
                continue
            seen.add(w)
            out.append(w)
        return out

    def _set_suggestions_from_candidates(self, selected_word: str, candidates: List[str]):
        ordered = self._unique_words([selected_word] + list(candidates))
        alternatives = [w for w in ordered if w != selected_word]
        if len(alternatives) < self._SUGGESTION_CHIP_COUNT:
            if selected_word and selected_word not in alternatives:
                alternatives.append(selected_word)
        while len(alternatives) < self._SUGGESTION_CHIP_COUNT and ordered:
            alternatives.append(ordered[min(len(alternatives), len(ordered) - 1)])
        self._suggestion_words = alternatives[: self._SUGGESTION_CHIP_COUNT]
        self._layout_suggestion_chips()

    def _clear_suggestions(self):
        self._suggestion_words = []
        self._layout_suggestion_chips()

    def _latest_swipe_word_record(self) -> Optional[SwipeWordRecord]:
        if not self._swipe_word_history:
            return None
        return self._swipe_word_history[-1]

    def _sync_swipe_history_state(self):
        record = self._latest_swipe_word_record()
        if record is None:
            self._swipe_candidates = []
            self._swipe_best = ""
            self._swipe_confidence = 0.0
            self._clear_suggestions()
            self._flick_window_active = False
            return

        self._swipe_candidates = list(record.candidates)
        self._swipe_best = record.selected_word
        self._swipe_confidence = float(record.confidence)
        self._set_suggestions_from_candidates(record.selected_word, record.candidates)

    def _remember_swipe_word(
        self,
        *,
        selected_word: str,
        candidates: List[str],
        emitted_text: str,
        confidence: float,
    ):
        self._swipe_word_history.append(
            SwipeWordRecord(
                selected_word=str(selected_word),
                candidates=list(candidates),
                emitted_text=str(emitted_text),
                confidence=float(confidence),
            )
        )
        if len(self._swipe_word_history) > self._SWIPE_HISTORY_LIMIT:
            self._swipe_word_history = self._swipe_word_history[-self._SWIPE_HISTORY_LIMIT :]
        self._sync_swipe_history_state()

    def _clear_swipe_word_history(self):
        self._swipe_word_history = []
        self._sync_swipe_history_state()
        self._cancel_flick_window()

    def _restore_latest_swipe_word_state(self):
        self._sync_swipe_history_state()
        if self._swipe_word_history and not self._swipe_active and not self._special_key_pinch_latched:
            self._start_flick_window()
        elif not self._swipe_word_history:
            self._cancel_flick_window()

    def _backspace_text(self, text: str):
        for _ in range(len(text)):
            self.action.tap_key("backspace")

    def _format_emitted_word(self, word: str) -> str:
        text = str(word)
        if self._caps_lock_active:
            text = "".join(ch.upper() if ch.isalpha() else ch for ch in text)
        if self.keyboard_swipe_auto_space:
            text += " "
        return text

    def _replace_emitted_text(self, old_text: str, replacement_text: str = ""):
        old_payload = str(old_text or "")
        replacement_payload = str(replacement_text or "")
        if hasattr(self.action, "replace_recent_text"):
            self.action.replace_recent_text(old_payload, replacement_payload)
            return
        self._backspace_text(old_payload)
        if replacement_payload:
            self.action.type_text(replacement_payload)

    def _reset_flick_detectors(self):
        self._flick_detector.reset()
        self._delete_flick_detector.reset()

    def _clear_flick_rearm(self):
        self._flick_rearm_pending = False
        self._flick_rearm_escape_direction = None
        self._flick_rearm_origin_point = None
        self._flick_rearm_last_point = None
        self._flick_rearm_stable_frames = 0

    def _begin_flick_rearm(self, point: Optional[Tuple[float, float]], *, escape_direction: Optional[str] = None):
        self._clear_flick_rearm()
        self._flick_rearm_pending = True
        self._flick_rearm_escape_direction = str(escape_direction) if escape_direction else None
        self._flick_rearm_origin_point = point
        self._flick_rearm_last_point = point
        self._reset_flick_detectors()

    def _seed_flick_detectors(
        self,
        start_point: Tuple[float, float],
        end_point: Tuple[float, float],
        now: float,
    ):
        seed_time = now - (1.0 / 30.0)
        self._flick_detector.add_sample(start_point, seed_time)
        self._flick_detector.add_sample(end_point, now)
        self._delete_flick_detector.add_sample(start_point, seed_time)
        self._delete_flick_detector.add_sample(end_point, now)

    def _flick_rearm_escape_reached(self, direction: Optional[str], dx: float, dy: float) -> bool:
        if not direction:
            return False
        if direction == "any":
            return (dx * dx + dy * dy) >= self._flick_rearm_escape_distance_sq
        if direction == "left":
            return dx >= self._FLICK_REARM_ESCAPE_DISTANCE
        if direction == "right":
            return dx <= -self._FLICK_REARM_ESCAPE_DISTANCE
        if direction == "up":
            return dy >= self._FLICK_REARM_ESCAPE_DISTANCE
        if direction == "down":
            return dy <= -self._FLICK_REARM_ESCAPE_DISTANCE
        return False

    def _update_flick_rearm(self, point: Optional[Tuple[float, float]], now: float) -> bool:
        if not self._flick_rearm_pending:
            return False
        if point is None:
            self._clear_flick_rearm()
            self._reset_flick_detectors()
            return False

        origin = self._flick_rearm_origin_point
        if origin is not None:
            origin_dx = point[0] - origin[0]
            origin_dy = point[1] - origin[1]
            if self._flick_rearm_escape_reached(self._flick_rearm_escape_direction, origin_dx, origin_dy):
                self._clear_flick_rearm()
                self._reset_flick_detectors()
                self._seed_flick_detectors(origin, point, now)
                return True

        if self._flick_rearm_last_point is None:
            self._flick_rearm_last_point = point
            return True

        dx = point[0] - self._flick_rearm_last_point[0]
        dy = point[1] - self._flick_rearm_last_point[1]
        if (dx * dx + dy * dy) <= self._flick_rearm_max_step_sq:
            self._flick_rearm_stable_frames += 1
        else:
            self._flick_rearm_stable_frames = 0
        self._flick_rearm_last_point = point

        if self._flick_rearm_stable_frames >= self._FLICK_REARM_STABLE_FRAMES:
            self._clear_flick_rearm()
            self._reset_flick_detectors()
        return True

    def _both_hands_present(self, hands_data: HandsData) -> bool:
        return hands_data.camera.has_left and hands_data.camera.has_right

    def _slot_id_to_swipe_token(self, slot_id: Optional[str]) -> Optional[str]:
        if not slot_id:
            return None
        return self._swipe_token_by_slot.get(str(slot_id))

    @classmethod
    def _modifier_family_for_slot(cls, slot_id: Optional[str]) -> Optional[str]:
        if not slot_id:
            return None
        return cls._MODIFIER_SLOT_TO_FAMILY.get(str(slot_id))

    @classmethod
    def _modifier_key_for_family(cls, family: str) -> Optional[str]:
        return cls._MODIFIER_FAMILY_TO_KEY.get(family)

    def _active_modifier_key_codes(self) -> List[str]:
        keys: List[str] = []
        for family in self._MODIFIER_PRESS_ORDER:
            if family not in self._active_modifiers:
                continue
            key_code = self._modifier_key_for_family(family)
            if key_code:
                keys.append(key_code)
        return keys

    def _active_modifier_families_ordered(self) -> List[str]:
        families: List[str] = []
        for family in self._MODIFIER_PRESS_ORDER:
            if family in self._active_modifiers:
                families.append(family)
        return families

    def _active_modifier_slot_ids(self) -> List[str]:
        slots: List[str] = []
        if self._caps_lock_active:
            slots.append("caps_lock")
        for family in self._MODIFIER_PRESS_ORDER:
            if family not in self._active_modifiers:
                continue
            slots.extend(self._MODIFIER_FAMILY_TO_SLOTS.get(family, ()))
        return slots

    def _toggle_caps_lock(self):
        self._caps_lock_active = not self._caps_lock_active
        self._last_event = "caps_on" if self._caps_lock_active else "caps_off"
        self._last_confidence = 1.0

    def _toggle_modifier_family(self, family: str):
        if family in self._active_modifiers:
            self._active_modifiers.remove(family)
            self._last_event = f"modifier_off:{family}"
        else:
            self._active_modifiers.add(family)
            self._last_event = f"modifier_on:{family}"
        self._last_confidence = 1.0

    def _tap_with_active_modifiers(self, key_code: str):
        oneshot_families = set(self._active_modifiers)
        key_to_tap = self._FN_KEY_TO_FUNCTION.get(key_code, key_code) if "fn" in oneshot_families else key_code
        is_alpha_key = isinstance(key_to_tap, str) and len(key_to_tap) == 1 and key_to_tap.isalpha()
        shift_from_modifiers = "shift" in oneshot_families
        effective_shift = shift_from_modifiers
        if is_alpha_key and self._caps_lock_active:
            # Emulate caps-lock behavior in gesture layer so it works across OS backends:
            # caps ON toggles letter case, and Shift inverts it.
            effective_shift = not shift_from_modifiers

        modifier_key_codes: List[str] = []
        for family in self._MODIFIER_PRESS_ORDER:
            if family == "shift":
                continue
            if family not in oneshot_families:
                continue
            key = self._modifier_key_for_family(family)
            if key:
                modifier_key_codes.append(key)

        if effective_shift:
            shift_key = self._modifier_key_for_family("shift")
            if shift_key:
                modifier_key_codes.append(shift_key)

        if not modifier_key_codes:
            self.action.tap_key(key_to_tap)
            self._last_event = f"tap:{key_to_tap}"
            self._last_confidence = 1.0
            if "fn" in oneshot_families:
                self._active_modifiers.clear()
            return

        self.action.tap_hotkey(modifier_key_codes + [key_to_tap])

        combo_tokens: List[str] = []
        if is_alpha_key and self._caps_lock_active:
            combo_tokens.append("caps")
        for family in self._MODIFIER_PRESS_ORDER:
            if family == "shift":
                continue
            if family in oneshot_families:
                combo_tokens.append(family)
        if effective_shift:
            combo_tokens.append("shift")
        combo_label = "+".join(combo_tokens + [key_to_tap])
        self._last_event = f"combo:{combo_label}"
        self._last_confidence = 1.0
        self._active_modifiers.clear()

    def _is_right_click_style_pinch(self, hands_data: HandsData) -> bool:
        if not hands_data.wrist.has_right:
            return False
        hand = hands_data.wrist.right
        return are_fingers_pinched(hand.thumb.tip, hand.middle.tip, self.pinch_threshold)

    def _right_pinch_distance(self, hands_data: HandsData) -> Optional[float]:
        if not hands_data.wrist.has_right:
            return None
        hand = hands_data.wrist.right
        return get_pinch_distance(hand.thumb.tip, hand.middle.tip)

    def _start_swipe(self):
        self._cancel_flick_window()
        self._replace_flick_cooldown_until = 0.0
        self._swipe_active = True
        self._swipe_release_counter = 0
        self._swipe_lost_frames = 0
        self._swipe_points = []
        self._swipe_trace_slots = []
        self._swipe_trace = []
        self._swipe_candidates = []
        self._swipe_best = ""
        self._swipe_confidence = 0.0

    def _cancel_swipe(self):
        self._swipe_active = False
        self._swipe_release_counter = 0
        self._swipe_lost_frames = 0
        self._swipe_points = []
        self._swipe_trace_slots = []
        self._swipe_trace = []

    def _capture_swipe_sample(self, hands_data: HandsData):
        right_hand = hands_data.camera.right if hands_data.camera.has_right else None
        frame = self._right_frame_for_swipe
        if right_hand is None or not right_hand.exists or frame is None:
            return

        tip = self._get_tip(right_hand, "index")
        if tip is None:
            return

        point = (tip[0], tip[1])
        if not self._swipe_points:
            self._swipe_points.append(point)
        else:
            dx = point[0] - self._swipe_points[-1][0]
            dy = point[1] - self._swipe_points[-1][1]
            if (dx * dx + dy * dy) >= self._swipe_point_min_distance_sq:
                self._swipe_points.append(point)

        slot = self._map_tip_to_slot("right", tip, frame)
        if slot is None:
            return
        slot_id = str(slot["id"])
        if not self._swipe_trace_slots or self._swipe_trace_slots[-1] != slot_id:
            self._swipe_trace_slots.append(slot_id)

        swipe_token = self._slot_id_to_swipe_token(slot_id)
        if swipe_token and (not self._swipe_trace or self._swipe_trace[-1] != swipe_token):
            self._swipe_trace.append(swipe_token)

    def _emit_word(self, word: str) -> str:
        text = self._format_emitted_word(word)
        self.action.type_text(text)
        return text

    def blocks_keyboard_mode_exit(self) -> str:
        if self._exit_fist_ready:
            return ""
        if self._swipe_active:
            return "Swipe gesture in progress"
        if self._special_key_pinch_latched:
            return "Key selection pinch is still latched"
        return ""

    def _right_hand_matches_keyboard_exit_pose(self, hands_data: HandsData) -> bool:
        if not hands_data.wrist.has_right:
            return False

        right_hand = hands_data.wrist.right
        if right_hand is None or not right_hand.exists:
            return False

        max_openness = float(self.config.get("keyboard_mode_exit_max_openness", 0.16))
        max_extension_ratio = float(self.config.get("keyboard_mode_exit_max_extension_ratio", 0.90))
        max_avg_finger_angle = float(self.config.get("keyboard_mode_exit_max_avg_finger_angle", 145.0))

        openness = get_hand_openness(right_hand, include_thumb=False)
        if openness > max_openness:
            return False

        finger_extensions = [
            get_finger_extension(right_hand.index),
            get_finger_extension(right_hand.middle),
            get_finger_extension(right_hand.ring),
            get_finger_extension(right_hand.pinky),
        ]
        if max(finger_extensions) > max_extension_ratio:
            return False
        if get_finger_extension(right_hand.thumb) > self._EXIT_FIST_MAX_THUMB_EXTENSION_RATIO:
            return False

        finger_angles = [
            get_finger_angle(right_hand.index),
            get_finger_angle(right_hand.middle),
            get_finger_angle(right_hand.ring),
            get_finger_angle(right_hand.pinky),
        ]
        avg_angle = sum(finger_angles) / len(finger_angles)
        return avg_angle <= max_avg_finger_angle

    def _current_right_slot_id(self, hands_data: HandsData) -> Optional[str]:
        right_hand = hands_data.camera.right if hands_data.camera.has_right else None
        frame = self._right_frame_for_swipe
        if right_hand is None or not right_hand.exists or frame is None:
            return None

        tip = self._get_tip(right_hand, "index")
        if tip is None:
            return None

        slot = self._map_tip_to_slot("right", tip, frame)
        if slot is None:
            return None
        return str(slot["id"])

    def _tap_slot_key(self, slot_id: str) -> bool:
        key_code = self._slot_to_key.get(str(slot_id))
        if not key_code:
            return False
        self._tap_with_active_modifiers(key_code)
        return True

    def _replace_last_swipe_word(self, suggestion_idx: int) -> bool:
        if suggestion_idx < 0 or suggestion_idx >= len(self._suggestion_words):
            return False
        replacement = self._suggestion_words[suggestion_idx]
        if not replacement:
            return False
        record = self._latest_swipe_word_record()
        if record is None or not record.emitted_text:
            return False

        emitted = self._format_emitted_word(replacement)
        self._replace_emitted_text(record.emitted_text, emitted)
        record.selected_word = replacement
        record.emitted_text = emitted
        record.confidence = 1.0
        self._sync_swipe_history_state()
        self._last_event = f"suggest:{replacement}"
        self._last_confidence = 1.0
        return True

    def _delete_last_swipe_word(self) -> bool:
        record = self._latest_swipe_word_record()
        if record is None or not record.emitted_text:
            return False

        deleted_word = record.selected_word
        self._replace_emitted_text(record.emitted_text, "")
        self._swipe_word_history.pop()
        self._sync_swipe_history_state()
        self._last_event = f"delete:{deleted_word}"
        self._last_confidence = 1.0
        return True

    def _commit_swipe(self, release_slot_id: Optional[str]):
        if release_slot_id is None:
            self._cancel_swipe()
            self._sync_swipe_history_state()
            return

        unique_keys = len(set(self._swipe_trace_slots))
        if unique_keys == 1 and self._swipe_trace_slots:
            self._tap_slot_key(self._swipe_trace_slots[-1])
            self._cancel_swipe()
            self._sync_swipe_history_state()
            return

        if len(self._swipe_points) < self.keyboard_swipe_min_points:
            self._cancel_swipe()
            self._sync_swipe_history_state()
            return
        if unique_keys < self.keyboard_swipe_min_unique_keys:
            self._cancel_swipe()
            self._sync_swipe_history_state()
            return

        best_word, confidence, candidates = self._swipe_decoder.decode(
            self._swipe_trace,
            top_k=self.keyboard_swipe_decode_top_k,
        )

        if not best_word:
            self._cancel_swipe()
            self._sync_swipe_history_state()
            return

        emitted = self._emit_word(best_word)
        self._remember_swipe_word(
            selected_word=best_word,
            candidates=candidates,
            emitted_text=emitted,
            confidence=confidence,
        )
        self._last_event = f"swipe:{best_word}"
        self._last_confidence = confidence
        self._cancel_swipe()
        self._start_flick_window()

    @staticmethod
    def _now_seconds() -> float:
        return time.monotonic()

    def _start_flick_window(self):
        if not self._swipe_word_history:
            self._cancel_flick_window()
            return
        self._flick_window_active = True
        self._flick_right_missing = False
        self._replace_flick_cooldown_until = 0.0
        self._clear_flick_rearm()
        self._reset_flick_detectors()

    def _cancel_flick_window(self):
        self._flick_window_active = False
        self._flick_right_missing = False
        self._clear_flick_rearm()
        self._reset_flick_detectors()

    def _is_deliberate_delete_flick(self) -> bool:
        motion = self._delete_flick_detector._motion
        if motion.frame_count < 3:
            return False

        displacement_vec, _ = motion.get_displacement()
        dx = abs(float(displacement_vec[0]))
        dy = float(displacement_vec[1])
        if dy < self._DELETE_FLICK_MIN_DISPLACEMENT:
            return False
        if dx > self._DELETE_FLICK_MAX_HORIZONTAL_DRIFT:
            return False

        if motion.get_path_smoothness() < self._DELETE_FLICK_MIN_SMOOTHNESS:
            return False
        return True

    def _replace_last_swipe_word_by_flick(self, direction: str) -> bool:
        suggestion_idx = None
        if direction == "left":
            suggestion_idx = 0
        elif direction == "up":
            suggestion_idx = 1
        elif direction == "right":
            suggestion_idx = 2
        elif direction == "down":
            return self._delete_last_swipe_word()
        if suggestion_idx is None:
            return False
        return self._replace_last_swipe_word(suggestion_idx)

    def _update_flick_window(self, hands_data: HandsData, *, start_pinch_active: bool, right_camera_present: bool) -> bool:
        if not self._flick_window_active:
            return False

        if start_pinch_active:
            self._cancel_flick_window()
            return False

        if not right_camera_present:
            self._flick_right_missing = True
            return True

        tip = self._current_right_tip(hands_data)
        if tip is None:
            self._flick_right_missing = True
            return True

        if self._flick_right_missing:
            self._reset_flick_detectors()
            self._flick_right_missing = False

        point = (tip[0], tip[1])
        now = self._now_seconds()
        if self._update_flick_rearm(point, now):
            return True

        self._delete_flick_detector.add_sample(point, now)
        replace_cooldown_active = now < self._replace_flick_cooldown_until
        if replace_cooldown_active:
            self._flick_detector.reset()
        else:
            self._flick_detector.add_sample(point, now)
            direction = self._flick_detector.detect()
            if direction:
                handled = self._replace_last_swipe_word_by_flick(direction)
                if handled and self._swipe_word_history:
                    self._replace_flick_cooldown_until = now + self.replace_flick_cooldown_seconds
                    self._begin_flick_rearm(point, escape_direction=direction)
                elif not self._swipe_word_history:
                    self._cancel_flick_window()
                return handled

        delete_direction = self._delete_flick_detector.detect()
        if delete_direction:
            if not self._is_deliberate_delete_flick():
                self._begin_flick_rearm(point, escape_direction=None)
                return True
            handled = self._replace_last_swipe_word_by_flick(delete_direction)
            if handled and self._swipe_word_history:
                self._replace_flick_cooldown_until = 0.0
                self._begin_flick_rearm(point, escape_direction="any")
            elif not self._swipe_word_history:
                self._cancel_flick_window()
            return handled

        return True

    def _update_swipe(self, hands_data: HandsData, camera_hands: Dict[str, object]):
        if not self.keyboard_swipe_enabled:
            self._cancel_swipe()
            self._cancel_flick_window()
            self._special_key_pinch_latched = False
            return

        right_camera_present = hands_data.camera.has_right and hands_data.camera.right.exists
        right_wrist_present = hands_data.wrist.has_right and hands_data.wrist.right.exists
        right_present = right_camera_present and right_wrist_present
        pinch_distance = self._right_pinch_distance(hands_data) if right_present else None
        self._last_pinch_value = pinch_distance
        start_pinch_active = (
            pinch_distance is not None and pinch_distance < self.pinch_threshold
        )
        release_reached = (
            pinch_distance is None or pinch_distance >= self.keyboard_swipe_release_pinch_threshold
        )

        if not right_camera_present:
            self._special_key_pinch_latched = False

        if self._special_key_pinch_latched:
            if release_reached:
                self._special_key_pinch_latched = False
                if self._swipe_word_history:
                    self._start_flick_window()
            return

        if self._update_flick_window(
            hands_data,
            start_pinch_active=start_pinch_active,
            right_camera_present=right_camera_present,
        ):
            return

        if self._swipe_active:
            if not right_camera_present:
                self._swipe_lost_frames += 1
                if self._swipe_lost_frames > self.keyboard_swipe_tracking_grace_frames:
                    self._cancel_swipe()
                    self._sync_swipe_history_state()
                return

            if self._swipe_lost_frames > 0:
                self._swipe_lost_frames = 0

            # Keep swipe alive until wrist landmarks return; do not force release.
            if not right_wrist_present:
                return

            if release_reached:
                self._swipe_release_counter += 1
                if self._swipe_release_counter >= self.keyboard_swipe_release_pending_frames:
                    release_slot_id = self._current_right_slot_id(hands_data)
                    self._commit_swipe(release_slot_id)
                return
            self._swipe_release_counter = 0
            self._capture_swipe_sample(hands_data)
            return

        if start_pinch_active:
            suggestion_idx = self._current_right_suggestion_index(hands_data)
            if suggestion_idx is not None:
                if self._replace_last_swipe_word(suggestion_idx):
                    self._special_key_pinch_latched = True
                return

            slot_id = self._current_right_slot_id(hands_data)
            if slot_id == "caps_lock":
                self._toggle_caps_lock()
                self._special_key_pinch_latched = True
                return

            modifier_family = self._modifier_family_for_slot(slot_id)
            if modifier_family:
                self._toggle_modifier_family(modifier_family)
                self._special_key_pinch_latched = True
                return

            if slot_id and self._active_modifiers:
                if self._tap_slot_key(slot_id):
                    self._special_key_pinch_latched = True
                return

            if slot_id and self._slot_id_to_swipe_token(slot_id) is None:
                if self._tap_slot_key(slot_id):
                    self._special_key_pinch_latched = True
                return
            if not self._swipe_active:
                self._start_swipe()
            self._capture_swipe_sample(hands_data)
            return

    def _pause(self, reason: str):
        if self._paused and self._status == reason:
            return

        if self.pause_on_hand_loss:
            self.action.release_all_keys()

        self._hovered_slots.clear()
        self._hovered_suggestion_idx = None
        self._cancel_swipe()
        self._clear_swipe_word_history()
        self._active_modifiers.clear()
        self._replace_flick_cooldown_until = 0.0
        self._paused = True
        self._resume_counter = 0
        self._status = reason
        self._last_event = ""
        self._last_confidence = 0.0

    def _resume_if_stable(self, hands_data: HandsData):
        if self.require_both_hands and not self._both_hands_present(hands_data):
            self._pause("Typing Paused: both hands required")
            return False

        self._resume_counter += 1
        if self._resume_counter < self.resume_stability_frames:
            self._status = "Typing Paused: waiting for stable hands..."
            return False

        self._paused = False
        self._status = "Keyboard Ready (Swipe)"
        return True

    def _update_overlay_only(self, hands_data: HandsData):
        self._exit_fist_ready = self._right_hand_matches_keyboard_exit_pose(hands_data)
        camera_hands = self._get_camera_hands(hands_data.camera)
        layout = self._surface.update_layout(
            hands_data,
            paused=self._paused,
            rows=self._rows_unified,
        )
        self._active_frames = {
            "left": layout.active_frames.get("left"),
            "right": layout.active_frames.get("right"),
        }
        self._right_frame_for_swipe = layout.unified_frame
        self._drag_bounds_by_side = dict(layout.drag_bounds_by_side)
        self._surface_extra_overlay = dict(layout.extra_overlay)
        self._set_overlay_keys(layout.overlay_keys)
        unified_frame = self._right_frame_for_swipe
        active_frames = self._active_frames

        if self.require_both_hands and not self._both_hands_present(hands_data):
            self._pause("Typing Paused: both hands required")
            return False

        if self._paused:
            self._resume_if_stable(hands_data)
            if self._paused:
                return False

        left_present = camera_hands.get("left") is not None and camera_hands["left"].exists
        right_present = camera_hands.get("right") is not None and camera_hands["right"].exists
        if self.require_both_hands and (not left_present or not right_present):
            self._pause("Typing Paused: both hands required")
            return False

        hovered_slots = set()
        self._hovered_suggestion_idx = None
        self._right_index_hover_point = None
        for side in ("left", "right"):
            frame = unified_frame if unified_frame is not None else active_frames.get(side)
            camera_hand = camera_hands.get(side)
            if frame is None or camera_hand is None or not camera_hand.exists:
                continue

            for finger_name in self._finger_names():
                tip = self._get_tip(camera_hand, finger_name)
                if tip is None:
                    continue
                if side == "right" and finger_name == "index":
                    self._right_index_hover_point = (tip[0], tip[1])
                slot = self._map_tip_to_slot(side, tip, frame)
                if slot is not None:
                    hovered_slots.add(str(slot["id"]))

                if side == "right":
                    suggestion_idx = self._suggestion_index_at_point((tip[0], tip[1]))
                    if suggestion_idx is not None:
                        self._hovered_suggestion_idx = suggestion_idx

        self._hovered_slots = hovered_slots
        self._update_swipe(hands_data, camera_hands)
        self._status = "Keyboard Ready (Swipe)"
        return False

    def update(self, hands_data: HandsData, frame_capture_ts_ns=None):
        # frame_capture_ts_ns intentionally unused for swipe MVP.
        return self._update_overlay_only(hands_data)

    def detect_gesture(self, hands_data: HandsData):
        return True, hands_data

    def execute_action(self, data):
        return

    def reset(self):
        self.action.release_all_keys()
        self._hovered_slots.clear()
        self._overlay_keys = []
        self._overlay_by_id = {}
        self._active_frames = {"left": None, "right": None}
        self._drag_bounds_by_side = {}
        self._anchor_avg = {"left": None, "right": None}
        self._size_avg = {"left": None, "right": None}
        self._surface_extra_overlay = {}
        self._right_index_hover_point = None
        self._right_frame_for_swipe = None
        self._swipe_active = False
        self._swipe_points = []
        self._swipe_trace_slots = []
        self._swipe_trace = []
        self._swipe_candidates = []
        self._swipe_best = ""
        self._swipe_confidence = 0.0
        self._swipe_release_counter = 0
        self._swipe_lost_frames = 0
        self._special_key_pinch_latched = False
        self._last_pinch_value = None
        self._exit_fist_ready = False
        self._replace_flick_cooldown_until = 0.0
        self._swipe_word_history = []
        self._suggestion_words = []
        self._suggestion_chips = []
        self._hovered_suggestion_idx = None
        self._overlay_bounds = None
        self._cancel_flick_window()
        self._active_modifiers = set()
        self._paused = True
        self._resume_counter = 0
        self._status = "Keyboard Initializing..."
        self._last_event = ""
        self._last_confidence = 0.0
        self._surface.shutdown()

    @property
    def is_active(self):
        return not self._paused

    @property
    def current_state(self):
        return self._status

    def get_overlay_data(self):
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

        swipe_points = self._swipe_points
        if len(swipe_points) > 180:
            stride = max(1, len(swipe_points) // 180)
            swipe_points = swipe_points[::stride]

        suggestion_chips = []
        for chip in self._suggestion_chips:
            suggestion_chips.append(
                {
                    "id": chip["id"],
                    "index": chip["index"],
                    "text": chip.get("text", ""),
                    "x": chip["x"],
                    "y": chip["y"],
                    "w": chip["w"],
                    "h": chip["h"],
                    "hovered": self._hovered_suggestion_idx == chip["index"],
                }
            )

        fn_active = "fn" in self._active_modifiers
        shift_active = "shift" in self._active_modifiers
        overlay_keys = []
        for key in self._overlay_keys:
            key_view = dict(key)
            slot_id = str(key_view.get("id", ""))
            if fn_active:
                fn_key = self._FN_KEY_TO_FUNCTION.get(slot_id)
                if fn_key:
                    key_view["label"] = fn_key.upper()
            elif shift_active:
                shifted = key_view.get("shift_label") or self._shift_label_by_slot.get(slot_id)
                if shifted:
                    key_view["label"] = str(shifted)
            overlay_keys.append(key_view)

        overlay = {
            "enabled": True,
            "calibrated": not self._paused,
            "status": self._status,
            "layout_id": self._keyboard_layout_id,
            "theme_id": self._keyboard_theme_id,
            "keys": overlay_keys,
            "drag_bounds": drag_bounds,
            "hovered_keys": list(self._hovered_slots),
            "pressed_keys": self._active_modifier_slot_ids(),
            "last_event": self._last_event,
            "press_confidence": self._last_confidence,
            "finger_diagnostics": [],
            "calibration": {"active": False, "progress": 1.0},
            "swipe_active": self._swipe_active,
            "swipe_path_points": [{"x": p[0], "y": p[1]} for p in swipe_points],
            "swipe_trace": list(self._swipe_trace),
            "swipe_candidates": list(self._swipe_candidates),
            "swipe_best": self._swipe_best,
            "swipe_confidence": self._swipe_confidence,
            "suggestion_chips": suggestion_chips,
            "debug_hud": {
                "pinch_value": self._last_pinch_value,
                "lost_frames": self._swipe_lost_frames,
            },
        }
        if self._surface_extra_overlay:
            overlay.update(self._surface_extra_overlay)
        if self._right_index_hover_point is not None:
            overlay["hover_point"] = {
                "x": self._right_index_hover_point[0],
                "y": self._right_index_hover_point[1],
            }
        return overlay
