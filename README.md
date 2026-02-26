# Setup

## Prerequisites
- Python 3.11
- `uv`

## Install `uv` (Windows)
```powershell
winget install --id=astral-sh.uv -e
```

## Linux Camera Tuning (optional, for lower capture latency)
Install camera utilities:
```bash
sudo apt install v4l-utils
```

Inspect camera devices and supported formats:
```bash
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
```

Try low-latency capture settings (prefer MJPG):
```bash
v4l2-ctl -d /dev/video0 --set-fmt-video=width=640,height=480,pixelformat=MJPG
v4l2-ctl -d /dev/video0 --set-parm=30
```

Optional manual exposure tuning:
```bash
v4l2-ctl -d /dev/video0 -c exposure_auto=1
v4l2-ctl -d /dev/video0 -c exposure_absolute=200
```

Reset to common defaults:
```bash
v4l2-ctl -d /dev/video0 -c exposure_auto=3
v4l2-ctl -d /dev/video0 --set-fmt-video=width=640,height=480,pixelformat=YUYV
```

## Install dependencies
Run this from the repository root:
```powershell
uv sync
```

## Run the application
Run this from the repository root:
```powershell
uv run python main.py
```

## Run tests
Run all tests:
```bash
uv run python -m unittest discover -s tests
```

Run keyboard/swipe tests only:
```bash
uv run python -m unittest discover -s tests/keyboard
```

## Verify environment
```powershell
uv run python --version
```
Expected output starts with `Python 3.11`.

## Camera permission
If prompted by your OS, allow camera access for Python/terminal.

## Branching and PR Workflow
1. Create a new branch for each issue or task you are working on.
2. Commit and push all related changes to that branch with clear, descriptive commit messages.
3. Open a pull request from your task branch into `dev` (not `main`).
4. Keep `main` for final deliverables/production. After work is merged into `dev` and validated, merge to `main` later.
**Current Implementations**:

1. **MoveMouseGesture** (`backend/gestures/mouse_mode/MoveMouseGesture.py`)
   - Trigger: Only index finger extended (others curled)
   - Action: Move cursor to index fingertip position every frame
   - Priority: 1 (lowest - can be overridden by other gestures)
   - Update rate: 30 FPS (matches camera framerate)

2. **ScrollGesture** (`backend/gestures/mouse_mode/ScrollGesture.py`)
   - Trigger: Index + middle fingers extended (ring + pinky curled)
   - Action: Scroll based on vertical finger movement delta
   - Priority: 5 (medium)
   - Tracks frame-to-frame position changes for scroll amount

**State Machine Class**: `GestureStateMachine` in `backend/gestures/GestureStateMachine.py` (lines 20-122)

---

### 3. Motion Gesture Recognition

**Location**: `backend/gestures/GestureRecognizer.py` (lines 190-297)

**Purpose**: Validates complete motion trajectories before triggering (swipes, circles, complex patterns)

**State Diagram**:
```
            start pose      continuous motion
IDLE -------------------> MOTION_START -------------------> MOTION_IN_PROGRESS
 ^                            |                                      |
 |                            | timeout                             |
 |                            v                                      |
 |                            +                                      |
 |                            |           timeout or invalid path    |
 |<---------------------------+--------------------------------------+
 |                                                                   |
 |                        validate pattern                          |
 +<---------------------- MOTION_COMPLETE <-------------------------+
                                |
                          execute action
```

**Key Features**:
- **MotionTracker** (`backend/gestures/MotionTracker.py`) buffers positions for trajectory analysis
- Timeout mechanism: Max frames before abandoning motion
- Rich trajectory analysis capabilities:
  - Velocity and direction calculation
  - Total distance traveled vs. straight-line displacement
  - Swipe detection (axis-specific with direction)
  - Path smoothness analysis
  - Clench detection (closing hand motion)

**Current Implementations**: None yet (framework ready for implementation)

**Potential Use Cases**:
- Swipe left/right for browser navigation (Back/Forward)
- Swipe up/down for page scrolling or window switching
- Fist clench for grab/select actions
- Circle motions for custom hotkeys or commands
- Drawing letters/symbols for text input or commands
- Two-hand gestures for advanced controls

**State Machine Class**: `MotionStateMachine` in `backend/gestures/GestureStateMachine.py` (lines 124-218)

---

## Core Components

### Hand Tracking Pipeline

**`backend/HandTracker.py`** (QThread, lines 1-208)
- MediaPipe hand landmark detection (21 points per hand)
- Processes camera frames at approximately 30 FPS
- Converts landmarks to wrist-relative and screen coordinates
- Emits Qt signals for thread-safe communication with GUI
- Calls `Strategizer.strategize()` when hands are detected

**`backend/HandsData.py`** (lines 1-193)
- Elegant data structure for hand landmarks
- Dual coordinate spaces for different purposes
- Dot notation API for intuitive access:
  ```python
  hands_data.wrist.right.index.tip     # Normalized coordinates
  hands_data.camera.left.thumb.base    # Screen coordinates
  ```
- Finger class with joints array and tip/base properties
- Supports both single-hand and two-hand tracking

### Gesture Coordination

**`backend/Strategizer.py`** (lines 1-205)
- Central coordinator for all gesture recognizers
- Manages control modes: IDLE, MOUSE, KEYBOARD, HOTKEY
- Priority-based conflict resolution
- Mode switching logic (planned at line 139)
- Dynamic gesture addition/removal
- Current mode: MOUSE (4 active gestures)

**Priority Hierarchy**:
```
Priority 10: LeftClickGesture, RightClickGesture
Priority 5:  ScrollGesture
Priority 1:  MoveMouseGesture (baseline - always available)
```

**Conflict Resolution** (lines 147-159):
- Gestures sorted by priority (highest first)
- High-priority gestures (>= 5) block lower-priority ones when active
- Prevents simultaneous conflicting actions (e.g., clicking while moving)

### Action Execution

**`backend/Action.py`** (lines 1-179)
- OS-agnostic action executor
- Native API implementations (10-50x faster than PyAutoGUI):
  - **Windows**: ctypes + Win32 API (SetCursorPos, mouse_event)
  - **macOS**: Quartz CGEvent framework (CGEventCreateMouseEvent, CGEventPost)
- Public methods:
  - `move_cursor(x, y)` - Move mouse to screen coordinates
  - `left_click(x, y)` - Perform left click at position
  - `right_click(x, y)` - Perform right click at position
  - `scroll(amount)` - Vertical scrolling (positive = down, negative = up)

### Signal Processing

**`backend/LandmarkSmoother.py`** (lines 1-89)
- Moving average filter with configurable window size
- Default window: 5 frames
- Reduces jitter in hand tracking while maintaining responsiveness
- Separate smoothing for wrist-relative and camera-relative coordinates
- Per-landmark history buffers using deque for efficient updates

### Configuration Management

**`backend/GestureConfig.py`** (lines 1-121)
- JSON-based configuration manager
- Loads from `gesture_config.json` with fallback to defaults
- Dictionary-style access: `config['key']` or `config.get('key', default)`
- Save/load functionality for persistence
- Debug mode toggle

**Key Configuration Parameters**:
```python
{
    "finger_extension_angle": 155.0,        # Extended vs. curled threshold (degrees)
    "pinch_threshold": 0.15,                # Pinch detection distance (wrist-relative)
    "scroll_sensitivity": 100,              # Scroll speed multiplier
    "mouse_tracking_pending_frames": 1,     # Mouse gesture confirmation (instant)
    "click_pending_frames": 3,              # Click gesture confirmation (prevents accidents)
    "scroll_pending_frames": 2,             # Scroll gesture confirmation (balanced)
    "ending_frames": 2,                     # Cooldown before gesture reset
    "screen_safe_margin": 50,               # Pixels from edge (prevents hot corners)
    "debug_mode": true                      # Enable debug logging
}
```

---

## Gesture Detection Utilities

**`backend/gestures/GestureUtils.py`** (lines 1-148)

Provides core utilities for gesture detection:

- **`is_finger_extended(finger, angle_threshold)`**
  - Calculates joint angles using dot product
  - Returns True if finger angle > threshold (default: 155 degrees)
  - Used to distinguish extended fingers from curled ones

- **`are_fingers_pinched(finger1, finger2, threshold)`**
  - Euclidean distance between fingertips
  - Returns True if distance < threshold (default: 0.15 wrist-relative units)
  - Used for click detection and pinch gestures

- **`convert_camera_to_screen(point, screen_width, screen_height)`**
  - Maps normalized camera coordinates (0-1) to screen pixels
  - Accounts for coordinate system differences
  - Essential for cursor control

- **Additional utilities**:
  - `is_hand_fist()` - Detect closed hand
  - `get_hand_openness()` - Measure how open the hand is
  - `count_extended_fingers()` - Count extended fingers
  - Various finger extension helpers for quick checks

---

## Frontend Components

### Main Window

**`frontend/main_window.py`** (lines 1-120)
- PySide6 QMainWindow for application GUI
- Connects to HandTracker signals (thread-safe communication)
- Control buttons:
  - Start/Stop tracking
  - Hide/Show preview (tracking continues in background)
- Draws hand landmarks on video feed using Qt painter
- Real-time visualization of detected hands

### Video Display

**`frontend/video_widget.py`** (lines 1-31)
- Displays camera feed using Qt
- Converts OpenCV BGR frames to Qt QPixmap format
- Auto-scaling while maintaining aspect ratio
- Efficient frame updates via Qt signals

### Statistics Display

**`frontend/widgets/stats_widget.py`** (lines 1-45)
- Real-time FPS display with color coding:
  - Green: >= 25 FPS (good performance)
  - Yellow: 15-24 FPS (acceptable)
  - Red: < 15 FPS (poor performance)
- Hand count indicator (0, 1, or 2 hands detected)
- Performance monitoring using frame time deques

---

## Gesture Detection Pipeline

Complete data flow from camera to action execution:

```
Camera Feed (30 FPS)
    |
    v
HandTracker (QThread)
    |-- MediaPipe hand landmark detection
    |-- Convert to wrist-relative coordinates
    |-- Convert to camera-relative (screen) coordinates
    v
LandmarkSmoother
    |-- Apply moving average filter (5-frame window)
    |-- Reduce jitter while maintaining responsiveness
    v
HandsData
    |-- Structured hand landmark data
    |-- Dual coordinate systems (wrist + camera)
    v
Strategizer
    |-- Check mode-switching gestures first (planned)
    |-- Get current mode gesture recognizers
    |-- Sort by priority (highest first)
    v
Gesture Recognizers (by priority)
    |-- Snapshot: Check pose -> Trigger once
    |-- Continuous: Check pose -> Trigger every frame
    |-- Motion: Track trajectory -> Validate -> Trigger
    |-- Each updates its state machine
    v
State Machines
    |-- GestureStateMachine (Snapshot/Continuous)
    |-- MotionStateMachine (Motion gestures)
    |-- Handle debouncing and state transitions
    v
Action Executor
    |-- Translate gesture intent to OS action
    |-- Use native APIs for performance
    v
OS APIs
    |-- Windows: Win32 API (ctypes)
    |-- macOS: Quartz CGEvent framework
    v
System Input (Mouse/Keyboard)
```

---

## Extensibility

The architecture is designed for easy extension with new gestures and modes.

### Adding New Gestures

**1. Choose the appropriate base class**:
- `SnapshotGestureRecognizer` - One-time discrete actions
- `ContinuousGestureRecognizer` - Real-time continuous control
- `MotionGestureRecognizer` - Trajectory-based patterns

**2. Implement required methods**:

```python
from backend.gestures.GestureRecognizer import SnapshotGestureRecognizer

class MyCustomGesture(SnapshotGestureRecognizer):
    def __init__(self, action, priority=5, **kwargs):
        super().__init__(priority=priority, **kwargs)
        self.action = action

    def detect_gesture(self, hands_data):
        """
        Return True if the gesture pose is detected.
        Access hand data via hands_data.wrist.right.index.tip, etc.
        """
        # Your detection logic here
        return True  # or False

    def execute_action(self, hands_data):
        """
        Execute the action when gesture is confirmed.
        Called once per activation for SnapshotGestureRecognizer.
        """
        # Your action execution here
        self.action.left_click(x, y)
```

**3. Add to Strategizer**:

```python
# In Strategizer._initialize_mouse_mode() or other mode initializers
self.mouse_mode_gestures.append(
    MyCustomGesture(
        self.action,
        priority=8,  # Set appropriate priority
        pending_frames=3,
        ending_frames=2
    )
)
```

**4. Configure in gesture_config.json** (optional):
```json
{
    "my_custom_gesture_pending_frames": 3,
    "my_custom_gesture_sensitivity": 100
}
```

### Adding Motion Gestures

For trajectory-based gestures, use `MotionGestureRecognizer`:

```python
class SwipeLeftGesture(MotionGestureRecognizer):
    def detect_start_pose(self, hands_data):
        """Detect the starting pose (e.g., open palm facing camera)"""
        return True  # or False

    def detect_motion_in_progress(self, hands_data):
        """Return True if motion is still valid"""
        return True  # or False

    def validate_motion_pattern(self, motion_tracker):
        """Validate the complete trajectory"""
        # Use motion_tracker methods:
        # - motion_tracker.is_swipe('x', 'left')
        # - motion_tracker.get_velocity()
        # - motion_tracker.get_total_distance()
        return motion_tracker.is_swipe('x', 'left')

    def execute_action(self, hands_data):
        """Execute action when motion is validated"""
        # Your action here (e.g., browser back)
        pass
```


### Adding Mode-Switching Gestures

Mode-switching gestures are universal across all modes:

```python
class SwitchToMouseModeGesture(SnapshotGestureRecognizer):
    def __init__(self, strategizer, **kwargs):
        super().__init__(priority=15, **kwargs)  # High priority
        self.strategizer = strategizer

    def detect_gesture(self, hands_data):
        """Detect unique pose (e.g., thumbs up)"""
        return True  # or False

    def execute_action(self, hands_data):
        """Switch to mouse mode"""
        self.strategizer.set_mode(ControlMode.MOUSE)
```

Add to `_initialize_switch_mode()` in Strategizer:
```python
def _initialize_switch_mode(self):
    self.switch_mode_gestures = [
        SwitchToMouseModeGesture(self, pending_frames=5),
        SwitchToKeyboardModeGesture(self, pending_frames=5),
        # ... more mode switchers
    ]
```

## Running the Application

### Installation
```bash
# To install you must first have uv dependency manager (pip install uv)
uv sync # install dependencies
```

### Running
```bash
uv run main.py
```

### Controls
- **Start Tracking**: Begin hand detection and gesture recognition
- **Stop Tracking**: Pause gesture recognition
- **Hide Preview**: Continue tracking in background (lower CPU usage)

---

## Configuration

Edit `gesture_config.json` to customize behavior:

```json
{
    "finger_extension_angle": 155.0,
    "scroll_sensitivity": 100,
    "pinch_threshold": 0.15,
    "mouse_tracking_pending_frames": 1,
    "click_pending_frames": 3,
    "scroll_pending_frames": 2,
    "ending_frames": 2,
    "screen_safe_margin": 50,
    "debug_mode": true
}
```

**Tips**:
- Increase `finger_extension_angle` for more relaxed detection (easier to trigger)
- Increase `pinch_threshold` for easier click detection (may cause accidental clicks)
- Increase `*_pending_frames` to prevent accidental gesture triggers (less responsive)
- Increase `scroll_sensitivity` for faster scrolling
- Increase `screen_safe_margin` to prevent cursor from sticking to edges

