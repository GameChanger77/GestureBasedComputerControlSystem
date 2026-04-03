from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple

import numpy as np

from backend.HandsData import HandsData


HAND_LANDMARK_COUNT = 21
FINGER_CHAINS = (
    (1, 2, 3, 4),
    (5, 6, 7, 8),
    (9, 10, 11, 12),
    (13, 14, 15, 16),
    (17, 18, 19, 20),
)
LANDMARK_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
)


@dataclass(frozen=True)
class HandPoseTemplate:
    """Normalized single-hand pose template."""

    name: str
    landmarks: Tuple[Tuple[float, float, float], ...]

    def __post_init__(self):
        if len(self.landmarks) != HAND_LANDMARK_COUNT:
            raise ValueError(f"Expected {HAND_LANDMARK_COUNT} landmarks, got {len(self.landmarks)}")

    def as_array(self) -> np.ndarray:
        return np.asarray(self.landmarks, dtype=np.float32)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "landmarks": [[float(x), float(y), float(z)] for x, y, z in self.landmarks],
        }

    @classmethod
    def from_array(cls, name: str, landmarks: np.ndarray) -> "HandPoseTemplate":
        normalized = normalize_landmarks(landmarks)
        return cls(name=name, landmarks=tuple(tuple(float(coord) for coord in point) for point in normalized))

    @classmethod
    def from_dict(cls, data: dict) -> "HandPoseTemplate":
        return cls(
            name=str(data.get("name", "custom pose")),
            landmarks=tuple(tuple(float(coord) for coord in point) for point in data["landmarks"]),
        )


@dataclass(frozen=True)
class PoseMatcherConfig:
    enter_threshold: float = 0.24
    exit_threshold: float = 0.30
    conflict_threshold: float = 0.16
    landmark_weight: float = 0.72
    joint_angle_weight: float = 0.28
    fingertip_weight: float = 1.8

    def to_dict(self) -> dict:
        return {
            "enter_threshold": float(self.enter_threshold),
            "exit_threshold": float(self.exit_threshold),
            "conflict_threshold": float(self.conflict_threshold),
            "landmark_weight": float(self.landmark_weight),
            "joint_angle_weight": float(self.joint_angle_weight),
            "fingertip_weight": float(self.fingertip_weight),
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "PoseMatcherConfig":
        if not isinstance(data, dict):
            return cls()
        defaults = cls().to_dict()
        for key in defaults:
            if key in data:
                defaults[key] = float(data[key])
        return cls(**defaults)


@dataclass(frozen=True)
class PoseMatchResult:
    matched: bool
    score: float
    landmark_score: float
    joint_angle_score: float
    threshold: float


def normalize_landmarks(landmarks: Sequence[Sequence[float]]) -> np.ndarray:
    array = np.asarray(landmarks, dtype=np.float32)
    if array.shape != (HAND_LANDMARK_COUNT, 3):
        raise ValueError(f"Expected landmark array shape (21, 3), got {array.shape}")
    wrist = array[0]
    centered = array - wrist
    anchor = centered[9]
    scale = float(np.linalg.norm(anchor))
    if scale < 1e-6:
        scale = 1e-6
    return (centered / scale).astype(np.float32)


def hand_to_landmark_array(hand: HandsData.Hand | None) -> np.ndarray | None:
    if hand is None or not getattr(hand, "exists", False):
        return None
    landmarks = getattr(hand, "_landmarks", None)
    if landmarks is None:
        return None
    array = np.asarray(landmarks, dtype=np.float32)
    if array.shape != (HAND_LANDMARK_COUNT, 3):
        return None
    return array


def _safe_unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm < 1e-6:
        return np.zeros(3, dtype=np.float32)
    return (vector / norm).astype(np.float32)


def compute_joint_angles(landmarks: Sequence[Sequence[float]]) -> np.ndarray:
    array = np.asarray(landmarks, dtype=np.float32)
    angles: List[float] = []
    for chain in FINGER_CHAINS:
        full_chain = (0,) + chain
        for idx in range(1, len(full_chain) - 1):
            prev_point = array[full_chain[idx - 1]]
            current = array[full_chain[idx]]
            next_point = array[full_chain[idx + 1]]
            vec_a = _safe_unit(prev_point - current)
            vec_b = _safe_unit(next_point - current)
            dot = float(np.clip(np.dot(vec_a, vec_b), -1.0, 1.0))
            angles.append(math.acos(dot) / math.pi)
    return np.asarray(angles, dtype=np.float32)


def _landmark_weights(config: PoseMatcherConfig) -> np.ndarray:
    weights = np.ones(HAND_LANDMARK_COUNT, dtype=np.float32)
    for idx in (4, 8, 12, 16, 20):
        weights[idx] = config.fingertip_weight
    return weights


def compare_pose_templates(
    expected: HandPoseTemplate,
    observed: HandPoseTemplate | Sequence[Sequence[float]],
    config: PoseMatcherConfig | None = None,
) -> PoseMatchResult:
    config = config or PoseMatcherConfig()
    expected_array = expected.as_array()
    observed_array = observed.as_array() if isinstance(observed, HandPoseTemplate) else normalize_landmarks(observed)
    landmark_delta = np.linalg.norm(expected_array - observed_array, axis=1)
    landmark_score = float(np.average(landmark_delta, weights=_landmark_weights(config)))
    expected_angles = compute_joint_angles(expected_array)
    observed_angles = compute_joint_angles(observed_array)
    joint_angle_score = float(np.mean(np.abs(expected_angles - observed_angles)))
    score = (landmark_score * config.landmark_weight) + (joint_angle_score * config.joint_angle_weight)
    return PoseMatchResult(
        matched=score <= config.enter_threshold,
        score=score,
        landmark_score=landmark_score,
        joint_angle_score=joint_angle_score,
        threshold=config.enter_threshold,
    )


def match_live_pose(
    expected: HandPoseTemplate,
    observed_landmarks: Sequence[Sequence[float]],
    config: PoseMatcherConfig | None = None,
    was_active: bool = False,
) -> PoseMatchResult:
    config = config or PoseMatcherConfig()
    result = compare_pose_templates(expected, observed_landmarks, config=config)
    threshold = config.exit_threshold if was_active else config.enter_threshold
    return PoseMatchResult(
        matched=result.score <= threshold,
        score=result.score,
        landmark_score=result.landmark_score,
        joint_angle_score=result.joint_angle_score,
        threshold=threshold,
    )


def _rot_x(degrees: float) -> np.ndarray:
    radians = math.radians(degrees)
    return np.asarray(
        [
            [1.0, 0.0, 0.0],
            [0.0, math.cos(radians), -math.sin(radians)],
            [0.0, math.sin(radians), math.cos(radians)],
        ],
        dtype=np.float32,
    )


def _rot_z(degrees: float) -> np.ndarray:
    radians = math.radians(degrees)
    return np.asarray(
        [
            [math.cos(radians), -math.sin(radians), 0.0],
            [math.sin(radians), math.cos(radians), 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )


def build_pose_template(
    name: str,
    finger_curls: dict[str, float],
    thumb_curl: float = 0.45,
    pinch_pair: Tuple[str, str] | None = None,
) -> HandPoseTemplate:
    landmarks = np.zeros((HAND_LANDMARK_COUNT, 3), dtype=np.float32)
    landmarks[0] = np.asarray((0.0, 0.0, 0.0), dtype=np.float32)

    base_positions = {
        "thumb": np.asarray((-0.34, 0.06, 0.00), dtype=np.float32),
        "index": np.asarray((-0.18, 0.12, 0.00), dtype=np.float32),
        "middle": np.asarray((0.00, 0.14, 0.00), dtype=np.float32),
        "ring": np.asarray((0.18, 0.12, 0.00), dtype=np.float32),
        "pinky": np.asarray((0.34, 0.08, 0.00), dtype=np.float32),
    }
    lengths = {
        "thumb": (0.17, 0.14, 0.12, 0.10),
        "index": (0.20, 0.17, 0.14, 0.11),
        "middle": (0.22, 0.18, 0.15, 0.12),
        "ring": (0.20, 0.17, 0.14, 0.11),
        "pinky": (0.17, 0.14, 0.12, 0.10),
    }
    base_dirs = {
        "thumb": _safe_unit(np.asarray((-0.75, 0.55, -0.05), dtype=np.float32)),
        "index": _safe_unit(np.asarray((-0.08, 1.00, 0.00), dtype=np.float32)),
        "middle": _safe_unit(np.asarray((0.00, 1.00, 0.00), dtype=np.float32)),
        "ring": _safe_unit(np.asarray((0.08, 1.00, 0.00), dtype=np.float32)),
        "pinky": _safe_unit(np.asarray((0.12, 0.96, 0.00), dtype=np.float32)),
    }
    curl_angles = {
        "thumb": (18.0, 32.0, 48.0, 58.0),
        "index": (15.0, 34.0, 58.0, 72.0),
        "middle": (12.0, 36.0, 60.0, 74.0),
        "ring": (15.0, 38.0, 64.0, 76.0),
        "pinky": (18.0, 42.0, 68.0, 82.0),
    }
    chain_indices = {
        "thumb": (1, 2, 3, 4),
        "index": (5, 6, 7, 8),
        "middle": (9, 10, 11, 12),
        "ring": (13, 14, 15, 16),
        "pinky": (17, 18, 19, 20),
    }
    finger_twist = {"thumb": -35.0, "index": -9.0, "middle": 0.0, "ring": 9.0, "pinky": 16.0}

    for finger_name, indices in chain_indices.items():
        landmarks[indices[0]] = base_positions[finger_name]
        direction = base_dirs[finger_name]
        curl = float(thumb_curl if finger_name == "thumb" else finger_curls.get(finger_name, 0.0))
        twist = _rot_z(finger_twist[finger_name] * curl)

        current = base_positions[finger_name]
        for segment_idx, landmark_index in enumerate(indices[1:], start=1):
            angle = curl_angles[finger_name][segment_idx] * curl
            rotation = twist @ _rot_x(angle)
            direction = _safe_unit(rotation @ direction)
            current = current + (direction * lengths[finger_name][segment_idx])
            landmarks[landmark_index] = current

    if pinch_pair is not None:
        finger_a, finger_b = pinch_pair
        tip_index_a = chain_indices[finger_a][-1]
        tip_index_b = chain_indices[finger_b][-1]
        center = (landmarks[tip_index_a] + landmarks[tip_index_b]) / 2.0
        separation = np.asarray((0.02, 0.015, -0.018), dtype=np.float32)
        landmarks[tip_index_a] = center - separation
        landmarks[tip_index_b] = center + separation
        for joint_index in (chain_indices[finger_a][-2], chain_indices[finger_b][-2]):
            landmarks[joint_index] = ((landmarks[joint_index] * 0.65) + (center * 0.35)).astype(np.float32)

    return HandPoseTemplate.from_array(name, landmarks)


def _build_template_library() -> tuple[dict[str, HandPoseTemplate], dict[str, HandPoseTemplate]]:
    saved_templates = {
        "mouse_move": build_pose_template(
            "Mouse Move",
            finger_curls={"index": 0.0, "middle": 1.0, "ring": 1.0, "pinky": 1.0},
            thumb_curl=0.08,
        ),
        "left_click": build_pose_template(
            "Left Click",
            finger_curls={"index": 0.72, "middle": 0.54, "ring": 0.94, "pinky": 1.0},
            thumb_curl=0.46,
            pinch_pair=("thumb", "middle"),
        ),
        "right_click": build_pose_template(
            "Right Click",
            finger_curls={"index": 0.68, "middle": 0.78, "ring": 0.52, "pinky": 1.0},
            thumb_curl=0.44,
            pinch_pair=("thumb", "ring"),
        ),
        "scroll": build_pose_template(
            "Scroll",
            finger_curls={"index": 0.08, "middle": 0.06, "ring": 0.96, "pinky": 1.0},
            thumb_curl=0.58,
        ),
        "switch_to_keyboard": build_pose_template(
            "Switch To Keyboard",
            finger_curls={"index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
            thumb_curl=0.05,
        ),
        "switch_to_hotkey": build_pose_template(
            "Switch To Hotkey",
            finger_curls={"index": 0.82, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
            thumb_curl=0.34,
            pinch_pair=("thumb", "index"),
        ),
        "switch_to_mouse": build_pose_template(
            "Switch To Mouse",
            finger_curls={"index": 1.0, "middle": 1.0, "ring": 1.0, "pinky": 1.0},
            thumb_curl=0.96,
        ),
    }
    preview_templates = {
        "mouse_move": build_pose_template(
            "Mouse Move Preview",
            finger_curls={"index": 0.0, "middle": 1.0, "ring": 1.0, "pinky": 1.0},
            thumb_curl=0.0,
        ),
        "left_click": build_pose_template(
            "Left Click Preview",
            finger_curls={"index": 0.82, "middle": 0.48, "ring": 0.98, "pinky": 1.0},
            thumb_curl=0.34,
            pinch_pair=("thumb", "middle"),
        ),
        "right_click": build_pose_template(
            "Right Click Preview",
            finger_curls={"index": 0.76, "middle": 0.82, "ring": 0.44, "pinky": 1.0},
            thumb_curl=0.36,
            pinch_pair=("thumb", "ring"),
        ),
        "scroll": build_pose_template(
            "Scroll Preview",
            finger_curls={"index": 0.08, "middle": 0.06, "ring": 0.94, "pinky": 1.0},
            thumb_curl=0.52,
        ),
        "switch_to_keyboard": build_pose_template(
            "Switch To Keyboard Preview",
            finger_curls={"index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
            thumb_curl=0.02,
        ),
        "switch_to_hotkey": build_pose_template(
            "Switch To Hotkey Preview",
            finger_curls={"index": 0.76, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
            thumb_curl=0.28,
            pinch_pair=("thumb", "index"),
        ),
        "switch_to_mouse": build_pose_template(
            "Switch To Mouse Preview",
            finger_curls={"index": 1.0, "middle": 1.0, "ring": 1.0, "pinky": 1.0},
            thumb_curl=0.98,
        ),
    }
    return saved_templates, preview_templates


def build_default_templates() -> dict[str, HandPoseTemplate]:
    saved_templates, _preview_templates = _build_template_library()
    return saved_templates


def build_preview_templates() -> dict[str, HandPoseTemplate]:
    _saved_templates, preview_templates = _build_template_library()
    return preview_templates
