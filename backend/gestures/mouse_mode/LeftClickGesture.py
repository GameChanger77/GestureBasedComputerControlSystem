import math
import time

from backend.gestures.GestureRecognizer import SnapshotGestureRecognizer
from backend.gestures.GestureUtils import are_fingers_pinched, camera_to_screen, is_finger_extended
from backend.HandsData import HandsData
from backend.gestures.GestureStateMachine import GestureState


class LeftClickGesture(SnapshotGestureRecognizer):
    """
    Detects thumb and middle finger pinch for primary mouse interactions.

    Activated when:
    - Thumb tip and middle finger tip are pinched together
    - Release after a confirmed pinch = single click
    - Sustained steady hold = double click
    - Sustained pinch with larger movement = left-click drag

    Priority: High (overrides mouse tracking)
    """

    def __init__(
        self,
        action,
        screen_width,
        screen_height,
        priority,
        pinch_threshold,
        extension_threshold,
        pending_frames,
        ending_frames,
        double_click_hold_time=0.55,
        drag_deadzone_px=32,
    ):
        """
        Args:
            action: Action object for executing clicks
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            priority: Gesture priority (default=10, high priority)
            pinch_threshold: Distance threshold for pinch detection
            extension_threshold: Angle threshold for finger extension
            pending_frames: Frames to confirm gesture
            ending_frames: Frames in ending state
            double_click_hold_time: Time to hold a steady pinch for double-click
            drag_deadzone_px: Movement required before the pinch becomes a drag
        """
        super().__init__(action, priority, pending_frames, ending_frames)
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.pinch_threshold = pinch_threshold
        self.extension_threshold = extension_threshold
        self.thumb_extension_threshold = max(110.0, float(extension_threshold) - 25.0)
        self.double_click_hold_time = max(0.05, float(double_click_hold_time))
        self.drag_deadzone_px = max(4, int(drag_deadzone_px))
        self.double_click_stationary_threshold_px = max(4.0, float(self.drag_deadzone_px) * 0.5)
        self.suppresses_lower_priorities_while_active = True

        self.gesture_start_time = None
        self.click_position = None
        self.latest_position = None
        self.drag_active = False
        self.gesture_completed = False

    def detect_gesture(self, hands_data: HandsData):
        """
        Detect if thumb and middle finger are pinched.

        Returns:
            tuple: (detected, (screen_x, screen_y))
        """
        if not hands_data.wrist.has_right or not hands_data.camera.has_right:
            return False, None

        hand_wrist = hands_data.wrist.right
        hand_camera = hands_data.camera.right

        thumb_tip = hand_wrist.thumb.tip
        middle_tip = hand_wrist.middle.tip

        if not are_fingers_pinched(thumb_tip, middle_tip, self.pinch_threshold):
            return False, None

        if not is_finger_extended(hand_wrist.thumb, threshold=self.thumb_extension_threshold):
            return False, None

        if is_finger_extended(hand_wrist.ring, threshold=self.extension_threshold):
            return False, None
        if is_finger_extended(hand_wrist.pinky, threshold=self.extension_threshold):
            return False, None

        index_tip = hand_camera.index.tip
        if index_tip is None:
            return False, None

        screen_x, screen_y = camera_to_screen(index_tip, self.screen_width, self.screen_height)
        return True, (screen_x, screen_y)

    def update(self, hands_data: HandsData, frame_capture_ts_ns=None):
        """
        Resolve the pinch into click, double-click, or drag.
        """
        detected, gesture_data = self.detect_gesture(hands_data)
        action_executed = False
        note = ""

        if detected and self.state_machine.is_idle and frame_capture_ts_ns is not None:
            self.action.set_pending_latency_origin_ts_ns(frame_capture_ts_ns)

        state, should_trigger, data = self.state_machine.update(detected, gesture_data)

        if detected and data is not None:
            self.latest_position = data

        if state == GestureState.ACTIVE and self.gesture_start_time is None and data is not None:
            self.gesture_start_time = time.time()
            self.click_position = data
            self.latest_position = data
            self.drag_active = False
            self.gesture_completed = False
            note = "Release for click, hold for double click, move to drag"
        elif state == GestureState.ACTIVE and self.gesture_start_time is not None and self.latest_position is not None:
            hold_duration = max(0.0, time.time() - self.gesture_start_time)
            current_position = self.latest_position
            displacement = self._distance_px(self.click_position, current_position)

            if self.drag_active:
                self.action.move_cursor(*current_position)
                action_executed = True
                note = "Dragging"
                self._set_debug_frame(
                    detected=detected,
                    should_trigger=should_trigger,
                    action_executed=action_executed,
                    state=state,
                    note=note,
                )
                return True

            if not self.gesture_completed and displacement >= self.drag_deadzone_px:
                self._begin_drag(current_position)
                action_executed = True
                note = "Drag started"
                self._set_debug_frame(
                    detected=detected,
                    should_trigger=should_trigger,
                    action_executed=action_executed,
                    state=state,
                    note=note,
                )
                return True

            if (
                not self.gesture_completed
                and hold_duration >= self.double_click_hold_time
                and displacement <= self.double_click_stationary_threshold_px
            ):
                self.action.double_click(*current_position)
                self.gesture_completed = True
                action_executed = True
                note = "Double click triggered"
                self._set_debug_frame(
                    detected=detected,
                    should_trigger=should_trigger,
                    action_executed=action_executed,
                    state=state,
                    note=note,
                )
                return True

            note = "Release for click, hold for double click, move to drag"
        elif state == GestureState.ENDING and self.drag_active:
            note = "Release pending"

        if state == GestureState.IDLE and self.gesture_start_time is not None:
            if self.drag_active:
                self.action.release_left_click()
                action_executed = True
                note = "Drag released"
            elif not self.gesture_completed and self.latest_position is not None:
                self.execute_single_click(self.latest_position)
                action_executed = True
                note = "Single click triggered"
            else:
                note = "Released"
            self._reset_interaction_state()

        self._set_debug_frame(
            detected=detected,
            should_trigger=should_trigger,
            action_executed=action_executed,
            state=state,
            note=note,
        )
        return action_executed

    def execute_single_click(self, data):
        """Perform single click."""
        if data is not None:
            screen_x, screen_y = data
            self.action.left_click(screen_x, screen_y)

    def _begin_drag(self, current_position):
        self.drag_active = True
        self.gesture_completed = True
        self.action.hold_left_click()
        if self.click_position is not None:
            self.action.move_cursor(*self.click_position)
        if current_position is not None and current_position != self.click_position:
            self.action.move_cursor(*current_position)

    @staticmethod
    def _distance_px(start_position, current_position):
        if start_position is None or current_position is None:
            return 0.0
        start_x, start_y = start_position
        current_x, current_y = current_position
        return math.hypot(float(current_x) - float(start_x), float(current_y) - float(start_y))

    def _reset_interaction_state(self):
        self.gesture_start_time = None
        self.click_position = None
        self.latest_position = None
        self.drag_active = False
        self.gesture_completed = False

    def reset(self):
        if self.drag_active:
            try:
                self.action.release_left_click()
            except Exception:
                pass
        self._reset_interaction_state()
        super().reset()

    def execute_action(self, data):
        """
        This method is overridden by update() to handle release/hold logic.
        """
        _ = data
