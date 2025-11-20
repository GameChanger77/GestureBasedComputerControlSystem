from enum import Enum


class GestureState(Enum):
    """
    Finite State Machine states for gesture recognition.

    For snapshot/continuous gestures:
    IDLE → PENDING → ACTIVE → ENDING → IDLE
           ↓                    ↓
           └────────────────────┘
             (gesture not confirmed)

    For motion gestures:
    IDLE → MOTION_START → MOTION_IN_PROGRESS → MOTION_COMPLETE → IDLE
           ↓                                      ↓
           └──────────────────────────────────────┘
                    (motion not completed)
    """
    IDLE = "idle"                           # No gesture detected
    PENDING = "pending"                     # Gesture shape detected, waiting for confirmation
    ACTIVE = "active"                       # Gesture confirmed and actively being performed
    ENDING = "ending"                       # Gesture ending, cleanup phase

    # Motion-specific states
    MOTION_START = "motion_start"           # Motion initiated (starting pose detected)
    MOTION_IN_PROGRESS = "motion_in_progress"  # Motion being performed (tracking trajectory)
    MOTION_COMPLETE = "motion_complete"     # Motion pattern validated and completed


class GestureStateMachine:
    """
    Manages state transitions for snapshot and continuous gestures with debouncing.
    """

    def __init__(self, pending_frames=3, ending_frames=2):
        """
        Initialize the state machine.

        Args:
            pending_frames: Number of consecutive frames needed to confirm gesture
            ending_frames: Number of frames to remain in ENDING state before returning to IDLE
        """
        self.state = GestureState.IDLE
        self.pending_frames = pending_frames
        self.ending_frames = ending_frames

        self._pending_counter = 0
        self._ending_counter = 0
        self._active_data = None

    def update(self, gesture_detected, gesture_data=None):
        """
        Update the state machine based on current frame detection.

        Args:
            gesture_detected: Boolean indicating if gesture shape is detected in current frame
            gesture_data: Optional data associated with the gesture

        Returns:
            tuple: (state, should_trigger_action, gesture_data)
        """
        should_trigger_action = False

        if self.state == GestureState.IDLE:
            if gesture_detected:
                self.state = GestureState.PENDING
                self._pending_counter = 1
                self._active_data = gesture_data

        elif self.state == GestureState.PENDING:
            if gesture_detected:
                self._pending_counter += 1
                self._active_data = gesture_data

                if self._pending_counter >= self.pending_frames:
                    self.state = GestureState.ACTIVE
                    should_trigger_action = True
            else:
                self.state = GestureState.IDLE
                self._pending_counter = 0
                self._active_data = None

        elif self.state == GestureState.ACTIVE:
            if gesture_detected:
                self._active_data = gesture_data
                should_trigger_action = True
            else:
                self.state = GestureState.ENDING
                self._ending_counter = 1

        elif self.state == GestureState.ENDING:
            if gesture_detected:
                self.state = GestureState.ACTIVE
                self._active_data = gesture_data
                should_trigger_action = True
            else:
                self._ending_counter += 1
                if self._ending_counter >= self.ending_frames:
                    self.state = GestureState.IDLE
                    self._ending_counter = 0
                    self._active_data = None

        return self.state, should_trigger_action, self._active_data

    def reset(self):
        """Force reset to IDLE state"""
        self.state = GestureState.IDLE
        self._pending_counter = 0
        self._ending_counter = 0
        self._active_data = None

    @property
    def is_active(self):
        """Check if gesture is currently active"""
        return self.state == GestureState.ACTIVE

    @property
    def is_idle(self):
        """Check if state machine is idle"""
        return self.state == GestureState.IDLE


class MotionStateMachine:
    """
    Manages state transitions for motion-based gestures.

    Motion gestures require tracking a complete trajectory before triggering.
    """

    def __init__(self, start_confirm_frames=2, timeout_frames=60):
        """
        Initialize the motion state machine.

        Args:
            start_confirm_frames: Frames needed to confirm motion start pose
            timeout_frames: Max frames for motion to complete before timeout
        """
        self.state = GestureState.IDLE
        self.start_confirm_frames = start_confirm_frames
        self.timeout_frames = timeout_frames

        self._start_counter = 0
        self._progress_counter = 0
        self._motion_data = None

    def update(self, start_detected, motion_in_progress, motion_complete, motion_data=None):
        """
        Update the motion state machine.

        Args:
            start_detected: Boolean indicating if starting pose is detected
            motion_in_progress: Boolean indicating if motion is currently happening
            motion_complete: Boolean indicating if complete motion pattern is validated
            motion_data: Data associated with the motion

        Returns:
            tuple: (state, should_trigger_action, motion_data)
        """
        should_trigger_action = False

        if self.state == GestureState.IDLE:
            if start_detected:
                self.state = GestureState.MOTION_START
                self._start_counter = 1
                self._motion_data = motion_data

        elif self.state == GestureState.MOTION_START:
            if start_detected:
                self._start_counter += 1
                if self._start_counter >= self.start_confirm_frames:
                    self.state = GestureState.MOTION_IN_PROGRESS
                    self._progress_counter = 0
            else:
                # Start pose lost before confirmation
                self.state = GestureState.IDLE
                self._start_counter = 0

        elif self.state == GestureState.MOTION_IN_PROGRESS:
            self._progress_counter += 1
            self._motion_data = motion_data

            if motion_complete:
                # Motion pattern validated!
                self.state = GestureState.MOTION_COMPLETE
                should_trigger_action = True
            elif not motion_in_progress or self._progress_counter >= self.timeout_frames:
                # Motion abandoned or timed out
                self.state = GestureState.IDLE
                self._progress_counter = 0
                self._motion_data = None

        elif self.state == GestureState.MOTION_COMPLETE:
            # Reset to IDLE after triggering
            self.state = GestureState.IDLE
            self._start_counter = 0
            self._progress_counter = 0
            self._motion_data = None

        return self.state, should_trigger_action, self._motion_data

    def reset(self):
        """Force reset to IDLE state"""
        self.state = GestureState.IDLE
        self._start_counter = 0
        self._progress_counter = 0
        self._motion_data = None

    @property
    def is_active(self):
        """Check if motion is in progress"""
        return self.state in [GestureState.MOTION_START, GestureState.MOTION_IN_PROGRESS]

    @property
    def is_idle(self):
        """Check if state machine is idle"""
        return self.state == GestureState.IDLE
