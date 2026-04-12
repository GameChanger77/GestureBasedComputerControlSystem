import math
import numpy as np

"""
Utility functions for gesture detection.

Provides common functions for:
- Finger state detection (raised, lowered, pinched)
- Distance calculations
- Hand pose analysis
"""


def is_finger_raised(finger, threshold_y=-0.3):
    """
    Check if a finger is raised (extended upward).

    DEPRECATED: Use is_finger_extended() instead for more reliable detection.

    Args:
        finger: Finger object from HandsData
        threshold_y: Y-coordinate threshold (wrist-relative, negative = above wrist)

    Returns:
        bool: True if finger tip is above threshold
    """
    if finger is None or finger.tip is None:
        return False

    # Finger is raised if tip is above (negative y) the threshold
    return finger.tip[1] < threshold_y


def calculate_angle(p1, p2, p3):
    """
    Calculate the angle at point p2 formed by points p1-p2-p3.

    Args:
        p1, p2, p3: Points as numpy arrays or tuples (x, y, z)

    Returns:
        float: Angle in degrees (0-180)
    """
    # Vectors from p2 to p1 and p2 to p3 (scalar math avoids tiny array allocations).
    v1x = p1[0] - p2[0]
    v1y = p1[1] - p2[1]
    v1z = p1[2] - p2[2]
    v2x = p3[0] - p2[0]
    v2y = p3[1] - p2[1]
    v2z = p3[2] - p2[2]

    v1_norm = math.sqrt(v1x * v1x + v1y * v1y + v1z * v1z)
    v2_norm = math.sqrt(v2x * v2x + v2y * v2y + v2z * v2z)

    if v1_norm <= 1e-6 or v2_norm <= 1e-6:
        return 0.0

    # Calculate angle using dot product
    cos_angle = (
        (v1x * v2x + v1y * v2y + v1z * v2z) / (v1_norm * v2_norm)
    )
    # Clamp to [-1, 1] to avoid numerical errors
    cos_angle = max(-1.0, min(1.0, cos_angle))
    angle_rad = math.acos(cos_angle)
    angle_deg = math.degrees(angle_rad)

    return angle_deg


def is_finger_extended(finger, threshold=155.0):
    """
    Check if a finger is extended based on joint angles.

    A finger has 4 joints: base (MCP), PIP, DIP, tip
    We calculate 3 angles at the middle joints.
    Extended finger: angles close to 180° (straight)
    Curled finger: angles much smaller (60-120°)

    Args:
        finger: Finger object from HandsData
        threshold: Minimum average angle in degrees to be considered extended (default=155)

    Returns:
        bool: True if finger is extended
    """
    if finger is None or len(finger.joints) < 4:
        return False

    # Per-frame cache on the Finger object (HandsData is recreated each frame).
    cache = getattr(finger, "_extended_cache", None)
    if cache is None:
        cache = {}
        setattr(finger, "_extended_cache", cache)

    cache_key = float(threshold)
    if cache_key in cache:
        return cache[cache_key]

    # Calculate angles at each joint (excluding first and last)
    angles = []

    # We have 4 joints: [base, pip, dip, tip] (indices 0, 1, 2, 3)
    # Calculate 3 angles:
    # - Angle at joint 1 (PIP): between joints 0-1-2
    # - Angle at joint 2 (DIP): between joints 1-2-3
    for i in range(1, len(finger.joints) - 1):
        angle = calculate_angle(finger.joints[i - 1], finger.joints[i], finger.joints[i + 1])
        angles.append(angle)

    if not angles:
        return False

    # Average angle - extended fingers have high average angles
    avg_angle = sum(angles) / len(angles)

    is_extended = avg_angle > threshold
    cache[cache_key] = is_extended
    return is_extended


def are_fingers_pinched(finger1_tip, finger2_tip, threshold):
    """
    Check if two fingertips are pinched together.

    Args:
        finger1_tip: First fingertip position (x, y, z)
        finger2_tip: Second fingertip position (x, y, z)
        threshold: Maximum distance to be considered pinched (wrist-relative units)

    Returns:
        bool: True if fingertips are close enough
    """
    if finger1_tip is None or finger2_tip is None:
        return False

    # Calculate Euclidean distance (optimized without numpy array creation)
    dx = finger1_tip[0] - finger2_tip[0]
    dy = finger1_tip[1] - finger2_tip[1]
    dz = finger1_tip[2] - finger2_tip[2]
    distance = (dx * dx + dy * dy + dz * dz) ** 0.5

    return distance < threshold


def get_pinch_distance(finger1_tip, finger2_tip):
    """
    Get distance between two fingertips.

    Args:
        finger1_tip: First fingertip position (x, y, z)
        finger2_tip: Second fingertip position (x, y, z)

    Returns:
        float: Euclidean distance
    """
    if finger1_tip is None or finger2_tip is None:
        return float('inf')

    dx = finger1_tip[0] - finger2_tip[0]
    dy = finger1_tip[1] - finger2_tip[1]
    dz = finger1_tip[2] - finger2_tip[2]

    return (dx * dx + dy * dy + dz * dz) ** 0.5


def count_raised_fingers(hand, threshold_y=-0.3):
    """
    Count how many fingers are raised on a hand.

    DEPRECATED: Use count_extended_fingers() instead.

    Args:
        hand: Hand object from HandsData
        threshold_y: Y-coordinate threshold for "raised"

    Returns:
        int: Number of raised fingers (0-5)
    """
    if not hand.exists:
        return 0

    count = 0
    fingers = [hand.thumb, hand.index, hand.middle, hand.ring, hand.pinky]

    for finger in fingers:
        if is_finger_raised(finger, threshold_y):
            count += 1

    return count


def count_extended_fingers(hand, threshold=0.6):
    """
    Count how many fingers are extended on a hand.

    Args:
        hand: Hand object from HandsData
        threshold: Extension threshold (0-1)

    Returns:
        int: Number of extended fingers (0-5)
    """
    if not hand.exists:
        return 0

    count = 0
    fingers = [hand.thumb, hand.index, hand.middle, hand.ring, hand.pinky]

    for finger in fingers:
        if is_finger_extended(finger, threshold):
            count += 1

    return count


def get_finger_extension(finger):
    """
    Get how extended a finger is (0 = curled, 1 = fully extended).

    Args:
        finger: Finger object

    Returns:
        float: Extension value [0-1]
    """
    if finger is None or len(finger.joints) < 4:
        return 0.0

    # Calculate total length along finger joints
    total_length = 0.0
    for i in range(len(finger.joints) - 1):
        j1 = finger.joints[i]
        j2 = finger.joints[i + 1]
        dx = j2[0] - j1[0]
        dy = j2[1] - j1[1]
        dz = j2[2] - j1[2]
        total_length += math.sqrt(dx * dx + dy * dy + dz * dz)

    # Calculate straight-line distance from base to tip
    base = finger.joints[0]
    tip = finger.joints[-1]
    dx = tip[0] - base[0]
    dy = tip[1] - base[1]
    dz = tip[2] - base[2]
    straight_distance = math.sqrt(dx * dx + dy * dy + dz * dz)

    # Extension ratio (approaches 1 when finger is straight)
    if total_length > 1e-6:
        return straight_distance / total_length

    return 0.0


def get_hand_openness(hand, include_thumb=True):
    """
    Get how open a hand is based on finger spread.

    Args:
        hand: Hand object
        include_thumb: Whether thumb spread should contribute to openness

    Returns:
        float: Openness value [0-1] where 1 is fully open
    """
    if not hand.exists:
        return 0.0

    # Calculate average distance between adjacent fingertips
    if include_thumb:
        fingertips = [
            hand.thumb.tip,
            hand.index.tip,
            hand.middle.tip,
            hand.ring.tip,
            hand.pinky.tip,
        ]
    else:
        fingertips = [
            hand.index.tip,
            hand.middle.tip,
            hand.ring.tip,
            hand.pinky.tip,
        ]

    total_spread = 0.0
    count = 0

    for i in range(len(fingertips) - 1):
        if fingertips[i] is not None and fingertips[i + 1] is not None:
            distance = get_pinch_distance(fingertips[i], fingertips[i + 1])
            total_spread += distance
            count += 1

    if count > 0:
        avg_spread = total_spread / count
        # Normalize to roughly [0-1] range (assuming max spread is around 1.5 units)
        return min(avg_spread / 1.5, 1.0)

    return 0.0


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _apply_camera_deadzone(value: float, leading_margin: float, trailing_margin: float) -> float:
    leading_margin = max(0.0, float(leading_margin))
    trailing_margin = max(0.0, float(trailing_margin))
    active_span = max(1e-6, 1.0 - leading_margin - trailing_margin)
    return _clamp_unit((float(value) - leading_margin) / active_span)


def apply_screen_interaction_sensitivity(value: float, sensitivity: float = 1.0) -> float:
    sensitivity = max(1.0, float(sensitivity))
    scaled = ((float(value) - 0.5) * sensitivity) + 0.5
    return _clamp_unit(scaled)


def apply_screen_interaction_sensitivity_to_point(point, sensitivity: float = 1.0):
    if point is None:
        return None
    x, y, z = point
    return (
        apply_screen_interaction_sensitivity(x, sensitivity=sensitivity),
        apply_screen_interaction_sensitivity(y, sensitivity=sensitivity),
        z,
    )


def camera_to_normalized_screen(
    camera_pos,
    *,
    flip_x=True,
    side_deadzone=0.0,
    top_deadzone=0.0,
    bottom_deadzone=0.0,
    sensitivity=1.0,
):
    """
    Normalize a camera-space point into the effective on-screen 0-1 range.

    Deadzones shrink the active camera range so reaching the view edges is not
    required to reach the display edges.
    """
    x, y, z = camera_pos
    x = float(x)
    y = float(y)

    if flip_x:
        x = 1.0 - x

    x = _apply_camera_deadzone(x, side_deadzone, side_deadzone)
    y = _apply_camera_deadzone(y, top_deadzone, bottom_deadzone)
    x = apply_screen_interaction_sensitivity(x, sensitivity=sensitivity)
    y = apply_screen_interaction_sensitivity(y, sensitivity=sensitivity)
    return x, y, z


def camera_to_screen(
    camera_pos,
    screen_width,
    screen_height,
    *,
    side_deadzone=0.0,
    top_deadzone=0.0,
    bottom_deadzone=0.0,
    flip_x=True,
    sensitivity=1.0,
):
    """
    Convert camera-relative coordinates to screen coordinates.

    Args:
        camera_pos: Tuple (x, y, z) in camera coordinates (0-1 range)
        screen_width: Screen width in pixels
        screen_height: Screen height in pixels
    Returns:
        tuple: (screen_x, screen_y) in pixel coordinates
    """
    x, y, _z = camera_to_normalized_screen(
        camera_pos,
        flip_x=flip_x,
        side_deadzone=side_deadzone,
        top_deadzone=top_deadzone,
        bottom_deadzone=bottom_deadzone,
        sensitivity=sensitivity,
    )

    # Convert from 0-1 range to screen pixel coordinates
    screen_x = int(x * screen_width)
    screen_y = int(y * screen_height)

    # Clamp to actual screen bounds so the cursor can reach the full display.
    screen_x = max(0, min(screen_width - 1, screen_x))
    screen_y = max(0, min(screen_height - 1, screen_y))

    return screen_x, screen_y


def is_hand_in_fist(hand, extension_threshold=0.3):
    """
    Check if hand is in a fist (all fingers curled).

    Args:
        hand: Hand object
        extension_threshold: Maximum extension to be considered curled

    Returns:
        bool: True if hand is in fist
    """
    if not hand.exists:
        return False

    fingers = [hand.index, hand.middle, hand.ring, hand.pinky]

    for finger in fingers:
        if get_finger_extension(finger) > extension_threshold:
            return False

    return True


def get_finger_angle(finger):
    """
    Get the average joint angle for a finger.

    Args:
        finger: Finger object

    Returns:
        float: Average angle in degrees (or 0 if invalid)
    """
    if finger is None or len(finger.joints) < 4:
        return 0.0

    angles = []

    for i in range(1, len(finger.joints) - 1):
        angle = calculate_angle(finger.joints[i - 1], finger.joints[i], finger.joints[i + 1])
        angles.append(angle)

    if not angles:
        return 0.0

    return sum(angles) / len(angles)


def are_only_fingers_extended(hand, extended_fingers, extension_threshold):
    """
    Check if ONLY the specified fingers are extended, and all others are curled.

    Thumb is always ignored for flexibility.

    Args:
        hand: Hand object
        extended_fingers: List of finger names that should be extended (e.g., ['index'] or ['index', 'middle'])
        extension_threshold: Minimum angle in degrees to be extended

    Returns:
        bool: True if only the specified fingers are extended

    Example:
        are_only_fingers_extended(hand, ['index'])  # Only index extended
        are_only_fingers_extended(hand, ['index', 'middle'])  # Only index+middle extended
    """
    if not hand.exists:
        return False

    # Per-frame cache on the Hand object keyed by requested finger set + threshold.
    hand_cache = getattr(hand, "_only_fingers_extended_cache", None)
    if hand_cache is None:
        hand_cache = {}
        setattr(hand, "_only_fingers_extended_cache", hand_cache)

    cache_key = (tuple(sorted(extended_fingers)), float(extension_threshold))
    cached_value = hand_cache.get(cache_key)
    if cached_value is not None:
        return cached_value

    # Check all non-thumb fingers
    all_fingers = ['index', 'middle', 'ring', 'pinky']

    for finger_name in all_fingers:
        finger = getattr(hand, finger_name)

        if finger_name in extended_fingers:
            # This finger should be extended
            is_ext = is_finger_extended(finger, threshold=extension_threshold)
            if not is_ext:
                hand_cache[cache_key] = False
                return False
        else:
            # This finger should be curled (NOT extended)
            is_ext = is_finger_extended(finger, threshold=extension_threshold)
            if is_ext:
                hand_cache[cache_key] = False
                return False

    hand_cache[cache_key] = True
    return True


def get_palm_normal(hand):
    """
    Estimate palm normal using wrist -> index base and wrist -> pinky base vectors.

    Returns:
        np.array([nx, ny, nz]) normalized, or zeros when invalid.
    """
    if hand is None or not hand.exists or hand.wrist is None:
        return np.array([0.0, 0.0, 0.0])

    index_base = hand.index.base
    pinky_base = hand.pinky.base
    if index_base is None or pinky_base is None:
        return np.array([0.0, 0.0, 0.0])

    wrist = np.array(hand.wrist)
    v1 = np.array(index_base) - wrist
    v2 = np.array(pinky_base) - wrist
    normal = np.cross(v1, v2)
    mag = np.linalg.norm(normal)
    if mag < 1e-6:
        return np.array([0.0, 0.0, 0.0])
    return normal / mag


def is_palm_facing_camera(hand, min_normal_z=0.35):
    """
    Approximate whether palm is facing camera.

    Uses absolute Z component of palm normal so it works for both hands without
    relying on handedness-specific sign conventions.
    """
    normal = get_palm_normal(hand)
    return abs(normal[2]) >= min_normal_z


def is_hand_fully_open(
    hand,
    extension_threshold=155.0,
    min_extended_fingers=4,
    openness_threshold=0.08,
    require_palm_facing_camera=False,
    min_palm_normal_z=0.35,
):
    """
    Check if hand is open enough for mode-switch entry.
    """
    if hand is None or not hand.exists:
        return False

    fingers = [hand.thumb, hand.index, hand.middle, hand.ring, hand.pinky]
    extended_count = sum(1 for finger in fingers if is_finger_extended(finger, threshold=extension_threshold))
    openness = get_hand_openness(hand)
    if extended_count < min_extended_fingers or openness < openness_threshold:
        return False
    if require_palm_facing_camera and not is_palm_facing_camera(hand, min_normal_z=min_palm_normal_z):
        return False
    return True
