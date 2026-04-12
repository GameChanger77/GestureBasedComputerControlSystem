from __future__ import annotations

FINGER_OPTIONS = [
    ("thumb", "Thumb"),
    ("index", "Index"),
    ("middle", "Middle"),
    ("ring", "Ring"),
    ("pinky", "Pinky"),
]

HAND_OPTIONS = [
    ("dominant", "Dominant"),
]

SPACE_OPTIONS = [
    ("wrist", "Wrist-Relative"),
    ("camera", "Camera"),
]

LANDMARK_OPTIONS = [("wrist", "Wrist")]
for finger_key, finger_label in FINGER_OPTIONS:
    if finger_key == "thumb":
        LANDMARK_OPTIONS.append((f"{finger_key}.base", f"{finger_label} Base"))
    LANDMARK_OPTIONS.append((f"{finger_key}.tip", f"{finger_label} Tip"))


CONDITION_DEFINITIONS = {
    "finger_extended": {
        "label": "Finger Extended",
        "fields": [
            {"name": "finger", "label": "Finger", "type": "enum", "options": FINGER_OPTIONS, "default": "index"},
            {"name": "value", "label": "Should Be Extended", "type": "bool", "default": True},
            {"name": "threshold_deg", "label": "Threshold (deg)", "type": "float", "min": 0.0, "max": 180.0, "step": 0.5, "decimals": 1, "default": 155.0},
        ],
    },
    "only_fingers_extended": {
        "label": "Only Specific Fingers Extended",
        "fields": [
            {"name": "fingers", "label": "Extended Fingers", "type": "multi_enum", "options": FINGER_OPTIONS[1:], "default": ["index"]},
            {"name": "threshold_deg", "label": "Threshold (deg)", "type": "float", "min": 0.0, "max": 180.0, "step": 0.5, "decimals": 1, "default": 155.0},
        ],
    },
    "pinch_distance_lt": {
        "label": "Pinch Distance Less Than",
        "fields": [
            {"name": "a", "label": "Point A", "type": "enum", "options": LANDMARK_OPTIONS, "default": "thumb.tip"},
            {"name": "b", "label": "Point B", "type": "enum", "options": LANDMARK_OPTIONS, "default": "index.tip"},
            {"name": "value", "label": "Distance", "type": "float", "min": 0.0, "max": 2.0, "step": 0.01, "decimals": 3, "default": 0.30},
            {"name": "space", "label": "Coordinate Space", "type": "enum", "options": SPACE_OPTIONS, "default": "wrist"},
        ],
    },
    "pinch_distance_gt": {
        "label": "Pinch Distance Greater Than",
        "fields": [
            {"name": "a", "label": "Point A", "type": "enum", "options": LANDMARK_OPTIONS, "default": "thumb.tip"},
            {"name": "b", "label": "Point B", "type": "enum", "options": LANDMARK_OPTIONS, "default": "index.tip"},
            {"name": "value", "label": "Distance", "type": "float", "min": 0.0, "max": 2.0, "step": 0.01, "decimals": 3, "default": 0.30},
            {"name": "space", "label": "Coordinate Space", "type": "enum", "options": SPACE_OPTIONS, "default": "wrist"},
        ],
    },
    "hand_openness_gt": {
        "label": "Hand Openness Greater Than",
        "fields": [
            {"name": "value", "label": "Openness", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01, "decimals": 3, "default": 0.08},
            {"name": "space", "label": "Coordinate Space", "type": "enum", "options": SPACE_OPTIONS, "default": "wrist"},
        ],
    },
    "hand_openness_lt": {
        "label": "Hand Openness Less Than",
        "fields": [
            {"name": "value", "label": "Openness", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01, "decimals": 3, "default": 0.16},
            {"name": "space", "label": "Coordinate Space", "type": "enum", "options": SPACE_OPTIONS, "default": "wrist"},
        ],
    },
    "hand_exists": {
        "label": "Hand Exists",
        "fields": [
            {"name": "hand", "label": "Hand", "type": "enum", "options": HAND_OPTIONS, "default": "dominant"},
        ],
    },
    "hand_count_eq": {
        "label": "Hand Count Equals",
        "fields": [
            {"name": "value", "label": "Hand Count", "type": "int", "min": 0, "max": 2, "default": 1},
        ],
    },
    "hand_fully_open": {
        "label": "Hand Fully Open",
        "fields": [
            {"name": "extension_threshold", "label": "Extension Threshold (deg)", "type": "float", "min": 0.0, "max": 180.0, "step": 0.5, "decimals": 1, "default": 155.0},
            {"name": "min_extended_fingers", "label": "Min Extended Fingers", "type": "int", "min": 1, "max": 5, "default": 4},
            {"name": "openness_threshold", "label": "Openness Threshold", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01, "decimals": 3, "default": 0.08},
            {"name": "require_palm_facing_camera", "label": "Require Palm Facing Camera", "type": "bool", "default": False},
            {"name": "min_palm_normal_z", "label": "Min Palm Facing Strength", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01, "decimals": 2, "default": 0.35},
        ],
    },
    "strict_fist": {
        "label": "Strict Fist",
        "fields": [
            {"name": "max_openness", "label": "Max Openness", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01, "decimals": 3, "default": 0.16},
            {"name": "max_extension_ratio", "label": "Max Extension Ratio", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01, "decimals": 3, "default": 0.90},
            {"name": "max_avg_finger_angle", "label": "Max Avg Finger Angle (deg)", "type": "float", "min": 0.0, "max": 180.0, "step": 0.5, "decimals": 1, "default": 145.0},
        ],
    },
}


def supported_condition_ops() -> list[str]:
    return list(CONDITION_DEFINITIONS.keys())
