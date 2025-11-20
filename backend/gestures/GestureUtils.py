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
    p1 = np.array(p1)
    p2 = np.array(p2)
    p3 = np.array(p3)

    # Vectors from p2 to p1 and p2 to p3
    v1 = p1 - p2
    v2 = p3 - p2

    # Normalize vectors
    v1_norm = np.linalg.norm(v1)
    v2_norm = np.linalg.norm(v2)

    if v1_norm < 1e-6 or v2_norm < 1e-6:
        return 0.0

    v1 = v1 / v1_norm
    v2 = v2 / v2_norm

    # Calculate angle using dot product
    cos_angle = np.dot(v1, v2)
    # Clamp to [-1, 1] to avoid numerical errors
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    angle_rad = np.arccos(cos_angle)
    angle_deg = np.degrees(angle_rad)

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

    joints = [np.array(j) for j in finger.joints]

    # Calculate angles at each joint (excluding first and last)
    angles = []

    # We have 4 joints: [base, pip, dip, tip] (indices 0, 1, 2, 3)
    # Calculate 3 angles:
    # - Angle at joint 1 (PIP): between joints 0-1-2
    # - Angle at joint 2 (DIP): between joints 1-2-3
    for i in range(1, len(joints) - 1):
        angle = calculate_angle(joints[i-1], joints[i], joints[i+1])
        angles.append(angle)

    if not angles:
        return False

    # Average angle - extended fingers have high average angles
    avg_angle = sum(angles) / len(angles)

    return avg_angle > threshold


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
        j1 = np.array(finger.joints[i])
        j2 = np.array(finger.joints[i + 1])
        total_length += np.linalg.norm(j2 - j1)

    # Calculate straight-line distance from base to tip
    base = np.array(finger.joints[0])
    tip = np.array(finger.joints[-1])
    straight_distance = np.linalg.norm(tip - base)

    # Extension ratio (approaches 1 when finger is straight)
    if total_length > 1e-6:
        return straight_distance / total_length

    return 0.0


def get_hand_openness(hand):
    """
    Get how open a hand is based on finger spread.

    Args:
        hand: Hand object

    Returns:
        float: Openness value [0-1] where 1 is fully open
    """
    if not hand.exists:
        return 0.0

    # Calculate average distance between adjacent fingertips
    fingertips = [
        hand.thumb.tip,
        hand.index.tip,
        hand.middle.tip,
        hand.ring.tip,
        hand.pinky.tip
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


def camera_to_screen(camera_pos, screen_width, screen_height, safe_margin=50):
    """
    Convert camera-relative coordinates to screen coordinates.

    Args:
        camera_pos: Tuple (x, y, z) in camera coordinates (0-1 range)
        screen_width: Screen width in pixels
        screen_height: Screen height in pixels
        safe_margin: Pixels from screen edges to prevent hot corners

    Returns:
        tuple: (screen_x, screen_y) in pixel coordinates
    """
    x, y, z = camera_pos

    # Flip x coordinate for mirror effect
    x = 1.0 - x

    # Convert from 0-1 range to screen pixel coordinates
    screen_x = int(x * screen_width)
    screen_y = int(y * screen_height)

    # Clamp to screen bounds with safe margin
    screen_x = max(safe_margin, min(screen_width - safe_margin - 1, screen_x))
    screen_y = max(safe_margin, min(screen_height - safe_margin - 1, screen_y))

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

    joints = [np.array(j) for j in finger.joints]
    angles = []

    for i in range(1, len(joints) - 1):
        angle = calculate_angle(joints[i-1], joints[i], joints[i+1])
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

    # Check all non-thumb fingers
    all_fingers = ['index', 'middle', 'ring', 'pinky']

    for finger_name in all_fingers:
        finger = getattr(hand, finger_name)
        avg_angle = get_finger_angle(finger)

        if finger_name in extended_fingers:
            # This finger should be extended
            is_ext = is_finger_extended(finger, threshold=extension_threshold)
            if not is_ext:
                return False
        else:
            # This finger should be curled (NOT extended)
            is_ext = is_finger_extended(finger, threshold=extension_threshold)
            if is_ext:
                return False

    return True
