import argparse
import difflib
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import mediapipe as mp

# Ensure project root is importable when running script directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.GestureConfig import GestureConfig
from backend.HandsData import HandsData
from backend.Strategizer import ControlMode, Strategizer
from backend.keyboard.KeyCodes import LOCK_KEYS, MODIFIER_KEYS, normalize_key


SHIFTED_DIGITS = {
    "1": "!",
    "2": "@",
    "3": "#",
    "4": "$",
    "5": "%",
    "6": "^",
    "7": "&",
    "8": "*",
    "9": "(",
    "0": ")",
}


SHIFTED_PUNCT = {
    "minus": "_",
    "equals": "+",
    "left_bracket": "{",
    "right_bracket": "}",
    "backslash": "|",
    "semicolon": ":",
    "quote": "\"",
    "comma": "<",
    "period": ">",
    "slash": "?",
    "backtick": "~",
}


PLAIN_PUNCT = {
    "minus": "-",
    "equals": "=",
    "left_bracket": "[",
    "right_bracket": "]",
    "backslash": "\\",
    "semicolon": ";",
    "quote": "'",
    "comma": ",",
    "period": ".",
    "slash": "/",
    "backtick": "`",
}


@dataclass
class TrialResult:
    text: str
    score: float
    overrides: Dict[str, object]
    taps: int
    downs: int
    ups: int


class MockAction:
    """
    Captures key events without injecting OS keypresses.
    """

    def __init__(self):
        self.buffer: List[str] = []
        self.modifiers_down = set()
        self.lock_state = {"caps_lock": False}
        self.tap_count = 0
        self.down_count = 0
        self.up_count = 0
        self.event_log: List[str] = []

    def _is_shift_active(self) -> bool:
        return "left_shift" in self.modifiers_down or "right_shift" in self.modifiers_down

    def _emit_char(self, key: str):
        shift = self._is_shift_active()
        caps = self.lock_state.get("caps_lock", False)

        if len(key) == 1 and key.isalpha():
            upper = shift ^ caps
            self.buffer.append(key.upper() if upper else key.lower())
            return

        if key in SHIFTED_DIGITS:
            self.buffer.append(SHIFTED_DIGITS[key] if shift else key)
            return

        if key in PLAIN_PUNCT:
            self.buffer.append(SHIFTED_PUNCT[key] if shift else PLAIN_PUNCT[key])
            return

        if key == "space":
            self.buffer.append(" ")
            return
        if key == "tab":
            self.buffer.append("\t")
            return
        if key == "enter":
            self.buffer.append("\n")
            return
        if key == "backspace":
            if self.buffer:
                self.buffer.pop()
            return

    def key_down(self, key_code: str):
        key = normalize_key(key_code)
        self.down_count += 1
        self.event_log.append(f"down:{key}")
        if key in MODIFIER_KEYS:
            self.modifiers_down.add(key)

    def key_up(self, key_code: str):
        key = normalize_key(key_code)
        self.up_count += 1
        self.event_log.append(f"up:{key}")
        self.modifiers_down.discard(key)

    def tap_key(self, key_code: str):
        key = normalize_key(key_code)
        self.tap_count += 1
        self.event_log.append(f"tap:{key}")
        if key in LOCK_KEYS:
            if key == "caps_lock":
                self.lock_state["caps_lock"] = not self.lock_state["caps_lock"]
            return
        self._emit_char(key)

    def release_all_keys(self):
        self.modifiers_down.clear()

    # Mouse/other no-op methods for compatibility
    def move_mouse_absolute(self, *_args, **_kwargs):
        return

    def left_click(self, *_args, **_kwargs):
        return

    def right_click(self, *_args, **_kwargs):
        return

    def scroll(self, *_args, **_kwargs):
        return

    @property
    def text(self) -> str:
        return "".join(self.buffer)


class ConfigShim:
    """
    Minimal config adapter for Strategizer/Gestures without loading files each trial.
    """

    def __init__(self, values: Dict[str, object]):
        self.config = values

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def __getitem__(self, key: str):
        return self.config[key]


def ordered_match_count(text: str, target: str) -> int:
    j = 0
    for ch in text:
        if j < len(target) and ch == target[j]:
            j += 1
    return j


def score_output(text: str, target: str, taps: int) -> float:
    """
    Lenient objective for practical typing quality on a reference clip.

    Prioritizes:
    - Mostly alphabetic output (few symbols/digits)
    - Roughly the right number of letters/taps
    - Some phrase similarity to target
    """
    text_l = text.lower().replace("\n", " ").replace("\t", " ")
    target_l = target.lower()

    letters_only = "".join(ch for ch in text_l if ch.isalpha())
    target_letters = "".join(ch for ch in target_l if ch.isalpha())

    ordered = ordered_match_count(text_l, target_l)
    ratio = difflib.SequenceMatcher(None, text_l[: max(len(target_l) * 3, 1)], target_l).ratio()
    letters_ratio = difflib.SequenceMatcher(
        None, letters_only[: max(len(target_letters) * 2, 1)], target_letters
    ).ratio()

    alpha_count = sum(ch.isalpha() for ch in text_l)
    digit_count = sum(ch.isdigit() for ch in text_l)
    punct_count = sum((not ch.isalnum()) and (not ch.isspace()) for ch in text_l)
    non_space_count = sum(not ch.isspace() for ch in text_l)
    alpha_ratio = alpha_count / max(1, alpha_count + digit_count + punct_count)

    target_letter_count = len(target_letters)  # "helloworld" => 10
    target_chars = len(target_l)  # "hello world" => 11
    target_taps = target_chars

    score = 0.0
    score += ordered * 7.0
    score += ratio * 70.0
    score += letters_ratio * 90.0
    score += max(0.0, 55.0 - abs(len(letters_only) - target_letter_count) * 7.0)
    score += max(0.0, 22.0 - abs(non_space_count - target_letter_count) * 3.0)
    score += max(0.0, 30.0 - abs(taps - target_taps) * 2.5)
    score += alpha_ratio * 70.0
    score -= digit_count * 4.0
    score -= punct_count * 5.0

    if "hello" in text_l:
        score += 20.0
    if "world" in text_l:
        score += 20.0
    if "hello world" in text_l:
        score += 300.0
    return score


def get_video_frames(video_path: Path, model_path: Path, frame_stride: int = 1) -> Tuple[List[HandsData], float]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 1e-6:
        fps = 30.0

    base_options = mp.tasks.BaseOptions
    hand_landmarker = mp.tasks.vision.HandLandmarker
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=base_options(model_asset_path=str(model_path)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    # Reset smoother so replay runs are deterministic.
    HandsData._smoother = None

    frames: List[HandsData] = []
    idx = 0
    with hand_landmarker.create_from_options(options) as detector:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if idx % frame_stride != 0:
                idx += 1
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = int((idx / fps) * 1000.0)
            result = detector.detect_for_video(mp_image, timestamp_ms)
            if result.hand_landmarks:
                hands_data = HandsData.from_detection_result(result)
            else:
                hands_data = HandsData({}, {})
            frames.append(hands_data)
            idx += 1

    cap.release()
    return frames, fps


def build_strategizer(config_values: Dict[str, object]) -> Tuple[Strategizer, MockAction]:
    base = GestureConfig.DEFAULT_CONFIG.copy()
    base["debug_mode"] = False
    base["keyboard_debug_log_interval_sec"] = 999.0
    base.update(config_values)
    cfg = ConfigShim(base)

    action = MockAction()
    strategizer = Strategizer(
        action=action,
        config=cfg,
        screen_width=1920,
        screen_height=1080,
    )
    strategizer.switch_mode_gestures = []
    strategizer.current_mode = ControlMode.KEYBOARD
    return strategizer, action


def replay_once(frames: List[HandsData], config_values: Dict[str, object]) -> TrialResult:
    strategizer, action = build_strategizer(config_values)
    for hands_data in frames:
        strategizer.strategize(hands_data)
    action.release_all_keys()
    out = action.text
    taps = action.tap_count
    return TrialResult(
        text=out,
        score=score_output(out, "hello world", taps),
        overrides=config_values.copy(),
        taps=taps,
        downs=action.down_count,
        ups=action.up_count,
    )


SEARCH_SPACE = {
    "keyboard_finger_anchor_row": [0.08, 0.14, 0.20, 0.26, 0.34, 0.42],
    "keyboard_finger_anchor_mix_x": [0.60, 0.78, 0.92, 1.00],
    "keyboard_finger_anchor_mix_y": [0.60, 0.78, 0.92, 1.00],
    "keyboard_hand_vertical_offset": [-0.080, -0.050, -0.030, -0.015, 0.000, 0.020, 0.040],
    "keyboard_hand_horizontal_offset_left": [-0.10, -0.06, -0.03, 0.0, 0.03, 0.06, 0.10],
    "keyboard_hand_horizontal_offset_right": [-0.10, -0.06, -0.03, 0.0, 0.03, 0.06, 0.10],
    "keyboard_hand_vertical_offset_left": [-0.08, -0.05, -0.03, -0.01, 0.0, 0.02, 0.04],
    "keyboard_hand_vertical_offset_right": [-0.08, -0.05, -0.03, -0.01, 0.0, 0.02, 0.04],
    "keyboard_hand_half_width_scale": [2.0, 2.6, 3.2, 3.8, 4.4, 5.0],
    "keyboard_hand_half_width_min": [0.14, 0.18, 0.22, 0.26, 0.30],
    "keyboard_hand_half_width_max": [0.30, 0.36, 0.42, 0.48, 0.55],
    "keyboard_hand_height_ratio": [0.50, 0.62, 0.72, 0.84, 0.96],
    "keyboard_wrist_ema_alpha": [0.08, 0.16, 0.24, 0.32, 0.44],
    "keyboard_hand_size_ema_alpha": [0.08, 0.16, 0.24, 0.32, 0.44],
    "keyboard_press_bend_threshold_deg": [8.0, 14.0, 22.0, 30.0, 38.0, 46.0],
    "keyboard_press_bend_delta_deg": [1.0, 4.0, 8.0, 12.0, 16.0, 20.0],
    "keyboard_press_radius_drop": [0.000, 0.006, 0.012, 0.020, 0.030, 0.040, 0.055],
    "keyboard_press_depth_threshold": [0.002, 0.006, 0.010, 0.014, 0.020],
    "keyboard_press_depth_velocity_threshold": [0.000, 0.010, 0.020, 0.040, 0.060],
    "keyboard_release_bend_threshold_deg": [4.0, 10.0, 16.0, 22.0, 28.0],
    "keyboard_release_radius_drop": [0.000, 0.004, 0.010, 0.016, 0.024],
    "keyboard_release_depth_threshold": [0.000, 0.002, 0.004, 0.008, 0.012],
    "keyboard_press_hover_frames": [1, 2],
    "keyboard_min_key_refractory_ms": [0, 20, 40, 70, 100, 130],
    "keyboard_min_global_key_interval_ms": [0, 10, 20, 30, 40],
    "keyboard_assign_hands_by_x": [True, False],
    "keyboard_flip_x_for_mapping": [True, False],
    "keyboard_require_both_hands": [True, False],
    "keyboard_use_thumb_fingers": [True, False],
    "keyboard_active_fingers": [
        ["index", "middle"],
        ["thumb", "index", "middle"],
        ["index", "middle", "ring"],
        ["thumb", "index", "middle", "ring", "pinky"],
    ],
}


def random_overrides(rng: random.Random) -> Dict[str, object]:
    return {key: rng.choice(values) for key, values in SEARCH_SPACE.items()}


def mutate_overrides(base: Dict[str, object], rng: random.Random, mutations: int = 4) -> Dict[str, object]:
    out = base.copy()
    keys = list(SEARCH_SPACE.keys())
    rng.shuffle(keys)
    for key in keys[:max(1, mutations)]:
        out[key] = rng.choice(SEARCH_SPACE[key])
    return out


def run_search(
    frames: List[HandsData],
    max_trials: int,
    seed: int = 7,
    seed_overrides: Optional[Dict[str, object]] = None,
) -> TrialResult:
    rng = random.Random(seed)

    baseline = replay_once(frames, {})
    best = baseline
    print(f"[BASELINE] score={baseline.score:.2f} taps={baseline.taps} text='{baseline.text[:120]}'")
    if "hello world" in baseline.text.lower():
        return baseline

    if seed_overrides:
        seeded = replay_once(frames, seed_overrides)
        snippet = seeded.text.replace("\n", "\\n")[:140]
        print(f"[SEED] score={seeded.score:.2f} taps={seeded.taps} text='{snippet}'")
        if seeded.score > best.score:
            best = seeded
        if "hello world" in seeded.text.lower():
            return seeded

    random_ratio = 0.6 if not seed_overrides else 0.25
    random_trials = int(max_trials * random_ratio)
    local_trials = max_trials - random_trials

    for i in range(1, random_trials + 1):
        overrides = random_overrides(rng)
        result = replay_once(frames, overrides)
        if result.score > best.score:
            best = result
            snippet = result.text.replace("\n", "\\n")[:140]
            print(f"[RANDOM {i}] NEW BEST score={best.score:.2f} taps={best.taps} text='{snippet}'")

        if "hello world" in result.text.lower():
            print(f"[RANDOM {i}] SUCCESS text contains 'hello world'")
            return result

    for i in range(1, local_trials + 1):
        if i <= local_trials * 0.5:
            mut_count = rng.choice([2, 3, 4, 5])
            overrides = mutate_overrides(best.overrides, rng, mutations=mut_count)
        else:
            seed_overrides = random_overrides(rng)
            seed_overrides.update(best.overrides)
            overrides = mutate_overrides(seed_overrides, rng, mutations=rng.choice([3, 4, 5, 6]))

        result = replay_once(frames, overrides)
        if result.score > best.score:
            best = result
            snippet = result.text.replace("\n", "\\n")[:140]
            print(f"[LOCAL {i}] NEW BEST score={best.score:.2f} taps={best.taps} text='{snippet}'")

        if "hello world" in result.text.lower():
            print(f"[LOCAL {i}] SUCCESS text contains 'hello world'")
            return result

    return best


def main():
    parser = argparse.ArgumentParser(description="Replay a typing video and tune config until 'hello world' appears.")
    parser.add_argument("--video", type=str, default="videos/2026-02-13 20-47-21.mp4")
    parser.add_argument("--model", type=str, default="backend/models/hand_landmarker.task")
    parser.add_argument("--max-trials", type=int, default=180)
    parser.add_argument("--frame-stride", type=int, default=1)
    parser.add_argument("--write-overrides", type=str, default="videos/hello_world_tuned_overrides.json")
    parser.add_argument("--seed-overrides", type=str, default="")
    args = parser.parse_args()

    video_path = Path(args.video)
    model_path = Path(args.model)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    print(f"[INFO] Loading frames from {video_path} ...")
    frames, fps = get_video_frames(video_path, model_path, frame_stride=max(1, args.frame_stride))
    print(f"[INFO] Loaded {len(frames)} frames (source fps={fps:.2f}, stride={max(1, args.frame_stride)})")

    seed_overrides = None
    if args.seed_overrides:
        seed_path = Path(args.seed_overrides)
        if seed_path.exists():
            with seed_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                if "overrides" in payload and isinstance(payload["overrides"], dict):
                    seed_overrides = payload["overrides"]
                else:
                    seed_overrides = payload

    best = run_search(
        frames,
        max_trials=max(1, args.max_trials),
        seed_overrides=seed_overrides,
    )
    success = "hello world" in best.text.lower()

    print("\n[RESULT]")
    print(f"success={success}")
    print(f"score={best.score:.2f}")
    print(f"taps={best.taps} downs={best.downs} ups={best.ups}")
    text_preview = best.text[:400].replace("\n", "\\n")
    print(f"text='{text_preview}'")
    print("overrides=" + json.dumps(best.overrides, indent=2))

    out_path = Path(args.write_overrides)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "success": success,
                "score": best.score,
                "taps": best.taps,
                "downs": best.downs,
                "ups": best.ups,
                "text": best.text,
                "overrides": best.overrides,
            },
            f,
            indent=2,
        )
    print(f"[INFO] Wrote best trial to {out_path}")

    if not success:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
