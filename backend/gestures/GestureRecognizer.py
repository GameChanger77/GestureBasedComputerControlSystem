from abc import ABC, abstractmethod
from backend.gestures.GestureStateMachine import GestureStateMachine, MotionStateMachine, GestureState
from backend.gestures.MotionTracker import MotionTracker
from backend.HandsData import HandsData


class GestureRecognizer(ABC):
    """
    Abstract base class for all gesture recognizers.

    Each gesture recognizer:
    1. Detects a specific gesture pattern from HandsData
    2. Manages its own state machine for debouncing
    3. Calls action methods directly when gesture is confirmed

    Subclasses must implement detect_gesture() and execute_action().
    """

    def __init__(self, action, priority=0):
        """
        Initialize the gesture recognizer.

        Args:
            action: Action object to execute actions on
            priority: Priority level for gesture conflicts (higher = more important)
        """
        self.action = action
        self.priority = priority

    @abstractmethod
    def detect_gesture(self, hands_data: HandsData):
        """
        Detect if the gesture is present in current frame.

        Args:
            hands_data: Current hand landmark data

        Returns:
            tuple: (detected: bool, data: any)
                - detected: True if gesture pattern is detected
                - data: Optional data needed for action execution
        """
        pass

    @abstractmethod
    def execute_action(self, data):
        """
        Execute the action associated with this gesture.

        Args:
            data: Data returned from detect_gesture()
        """
        pass

    @abstractmethod
    def update(self, hands_data: HandsData, frame_capture_ts_ns=None):
        """
        Update the gesture recognizer with new hand data.
        This method is implemented in the Gesture recognition classes that inherit from GestureRecognizer.
        MouseMoveGesture.py implements this for example.

        Args:
            hands_data: Current hand landmark data
            frame_capture_ts_ns: Frame capture timestamp (ns) for latency tracking

        Returns:
            bool: True if action was executed this frame
        """
        pass

    @abstractmethod
    def reset(self):
        """Reset the gesture state machine to IDLE"""
        pass

    @property
    @abstractmethod
    def is_active(self):
        """Check if this gesture is currently active"""
        pass

    @property
    @abstractmethod
    def current_state(self):
        """Get current state of the gesture"""
        pass


class SnapshotGestureRecognizer(GestureRecognizer):
    """
    Base class for snapshot gestures that trigger once when a pose is detected.

    Examples: pinch to click, finger raise to activate mode

    Snapshot gestures:
    - Detect a static hand pose
    - Trigger action once when pose is confirmed
    - Do not trigger again until pose is released and re-detected
    """

    def __init__(self, action, priority=0, pending_frames=3, ending_frames=2):
        """
        Args:
            pending_frames: Frames needed to confirm gesture
            ending_frames: Frames in ending state before reset
        """
        super().__init__(action, priority)
        self.state_machine = GestureStateMachine(pending_frames, ending_frames)
        self._already_triggered = False

    def update(self, hands_data: HandsData, frame_capture_ts_ns=None):
        """
        Update for snapshot gestures - only trigger once per activation.
        """
        detected, gesture_data = self.detect_gesture(hands_data)

        # Snapshot latency starts at first detection frame.
        if detected and self.state_machine.is_idle and frame_capture_ts_ns is not None:
            self.action.set_pending_latency_origin_ts_ns(frame_capture_ts_ns)

        state, should_trigger, data = self.state_machine.update(detected, gesture_data)

        # Only trigger on first frame of ACTIVE state
        if should_trigger and state == GestureState.ACTIVE and not self._already_triggered:
            self._already_triggered = True
            self.execute_action(data)
            return True
        elif state == GestureState.IDLE:
            self._already_triggered = False

        return False

    def reset(self):
        """Reset the gesture state machine"""
        self.state_machine.reset()
        self._already_triggered = False

    @property
    def is_active(self):
        """Check if gesture is currently active"""
        return self.state_machine.is_active

    @property
    def current_state(self):
        """Get current state"""
        return self.state_machine.state


class ContinuousGestureRecognizer(GestureRecognizer):
    """
    Base class for continuous gestures that trigger every frame while pose is held.

    Examples: mouse tracking, scrolling

    Continuous gestures:
    - Detect a pose that should be maintained
    - Trigger action every frame while pose is held
    - Typically have shorter debounce times for responsiveness
    """

    def __init__(self, action, priority=0, pending_frames=1, ending_frames=1):
        """
        Continuous gestures typically have shorter debounce for responsiveness.
        """
        super().__init__(action, priority)
        self.state_machine = GestureStateMachine(pending_frames, ending_frames)

    def update(self, hands_data: HandsData, frame_capture_ts_ns=None):
        """
        Update for continuous gestures - trigger every frame while active.
        """
        detected, gesture_data = self.detect_gesture(hands_data)

        # Continuous latency starts from current triggering frame.
        if detected and frame_capture_ts_ns is not None:
            self.action.set_pending_latency_origin_ts_ns(frame_capture_ts_ns)

        state, should_trigger, data = self.state_machine.update(detected, gesture_data)

        if should_trigger:
            self.execute_action(data)
            return True

        return False

    def reset(self):
        """Reset the gesture state machine"""
        self.state_machine.reset()

    @property
    def is_active(self):
        """Check if gesture is currently active"""
        return self.state_machine.is_active

    @property
    def current_state(self):
        """Get current state"""
        return self.state_machine.state


class MotionGestureRecognizer(GestureRecognizer):
    """
    Base class for motion-based gestures that require a complete trajectory.

    Examples: swipe left, clench fist, circle motion, custom hotkey motions

    Motion gestures:
    - Track hand position over time
    - Validate a complete motion pattern before triggering
    - Use MotionTracker for trajectory analysis
    - Only trigger when motion is successfully completed
    """

    def __init__(self, action, priority=0, buffer_frames=30, start_confirm_frames=2, timeout_frames=60):
        """
        Args:
            buffer_frames: Frames to keep in motion history
            start_confirm_frames: Frames to confirm motion start
            timeout_frames: Max frames before motion times out
        """
        super().__init__(action, priority)
        self.state_machine = MotionStateMachine(start_confirm_frames, timeout_frames)
        self.motion_tracker = MotionTracker(buffer_frames)

    @abstractmethod
    def detect_start_pose(self, hands_data: HandsData):
        """
        Detect if the starting pose for the motion is present.

        Returns:
            tuple: (detected: bool, start_data: any)
        """
        pass

    @abstractmethod
    def detect_motion_in_progress(self, hands_data: HandsData):
        """
        Detect if the motion is currently happening (for tracking).

        Returns:
            tuple: (in_progress: bool, tracking_position: tuple)
                - tracking_position: (x, y, z) position to add to motion buffer
        """
        pass

    @abstractmethod
    def validate_motion_pattern(self):
        """
        Validate if the complete motion pattern has been achieved.

        Uses self.motion_tracker to analyze the trajectory.

        Returns:
            tuple: (complete: bool, motion_data: any)
        """
        pass

    def detect_gesture(self, hands_data: HandsData):
        """
        For motion gestures, this is not used directly.
        Instead, use the three-phase detection methods.
        """
        raise NotImplementedError("Motion gestures use three-phase detection")

    def update(self, hands_data: HandsData, frame_capture_ts_ns=None):
        """
        Update for motion gestures - track trajectory and validate pattern.
        """
        # Detect current motion state
        start_detected, start_data = self.detect_start_pose(hands_data)
        in_progress, tracking_pos = self.detect_motion_in_progress(hands_data)
        motion_complete, motion_data = self.validate_motion_pattern()

        if start_detected and self.state_machine.is_idle and frame_capture_ts_ns is not None:
            self.action.set_pending_latency_origin_ts_ns(frame_capture_ts_ns)

        # Add position to tracker if motion is in progress
        if in_progress:
            self.motion_tracker.add_frame(tracking_pos)
        elif self.state_machine.is_idle:
            # Clear tracker when idle
            self.motion_tracker.clear()

        # Update state machine
        state, should_trigger, data = self.state_machine.update(
            start_detected, in_progress, motion_complete, motion_data
        )

        # Execute action if motion completed
        if should_trigger:
            self.execute_action(data)
            self.motion_tracker.clear()  # Reset tracker after action
            return True

        return False

    def reset(self):
        """Reset the motion gesture state machine"""
        self.state_machine.reset()
        self.motion_tracker.clear()

    @property
    def is_active(self):
        """Check if motion is in progress"""
        return self.state_machine.is_active

    @property
    def current_state(self):
        """Get current state"""
        return self.state_machine.state
