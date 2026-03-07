import cv2
import mediapipe as mp
import os
import platform
import time
from collections import deque
from threading import Condition, Thread
import numpy as np

from PySide6.QtCore import QThread, Signal
from paths import resource
from backend.HandsData import HandsData


class HandTracker(QThread):
    # Qt signals for thread-safe communication
    landmarks_detected = Signal(dict, object)  # landmarks_data, frame (or None)
    tracking_started = Signal()
    tracking_stopped = Signal()
    error_occurred = Signal(str)

    def __init__(
        self,
        strategizer,
        action,
        model_path=resource(r"backend/models/hand_landmarker.task"),
        num_hands=2,
        config=None,
    ):
        """
        Initialize the hand tracker.

        Args:
            strategizer: Strategizer instance
            action: Action instance
            model_path: Path to hand landmarker model
            num_hands: Maximum number of tracked hands
            config: GestureConfig instance (optional)
        """
        super().__init__()
        self.strategizer = strategizer
        self.action = action
        self.model_path = model_path
        self.num_hands = num_hands
        self.config = config

        # Camera configuration (set when tracking starts)
        self.camera_index = 0
        self.camera_width = 640
        self.camera_height = 480

        # Detection parameters
        self.min_detection_confidence = float(config.get('hand_min_detection_confidence', 0.5)) if config else 0.5
        self.min_presence_confidence = float(config.get('hand_min_presence_confidence', 0.5)) if config else 0.5
        self.min_tracking_confidence = float(config.get('hand_min_tracking_confidence', 0.5)) if config else 0.5

        # Performance config
        self.target_max_fps = int(config.get('target_max_fps', 60)) if config else 60
        self.camera_buffer_size = int(config.get('camera_buffer_size', 1)) if config else 1
        self.metrics_window = int(config.get('pipeline_metrics_window', 120)) if config else 120
        self.camera_target_fps = float(config.get('camera_target_fps', 30)) if config else 30.0
        self.camera_auto_exposure = bool(config.get('camera_auto_exposure', True)) if config else True
        self.camera_dynamic_exposure = bool(config.get('camera_dynamic_exposure', True)) if config else True
        self.camera_dynamic_exposure_target_luma = (
            float(config.get('camera_dynamic_exposure_target_luma', 112.0)) if config else 112.0
        )
        self.camera_dynamic_exposure_tolerance_luma = (
            float(config.get('camera_dynamic_exposure_tolerance_luma', 14.0)) if config else 14.0
        )
        self.camera_dynamic_exposure_step = (
            float(config.get('camera_dynamic_exposure_step', 1.0)) if config else 1.0
        )
        self.camera_dynamic_exposure_every_n_frames = (
            int(config.get('camera_dynamic_exposure_every_n_frames', 12)) if config else 12
        )
        self.camera_dynamic_exposure_min = (
            config.get('camera_dynamic_exposure_min', None) if config else None
        )
        self.camera_dynamic_exposure_max = (
            config.get('camera_dynamic_exposure_max', None) if config else None
        )
        self.camera_exposure_value = config.get('camera_exposure_value', None) if config else None
        self.camera_gain_value = config.get('camera_gain_value', None) if config else None
        self.camera_warmup_frames = int(config.get('camera_warmup_frames', 8)) if config else 8
        self.camera_readback_log = bool(config.get('camera_readback_log', True)) if config else True
        self.capture_latest_frame_only = bool(config.get('capture_latest_frame_only', True)) if config else True
        self.right_hand_only_processing = bool(config.get('right_hand_only_processing', False)) if config else False

        # Runtime state
        self.landmarker = None
        self.cap = None
        self.is_running = False
        self.preview_enabled = True
        self._stopped_emitted = False
        self._camera_readback = {}
        self._capture_thread = None
        self._frame_condition = Condition()
        self._latest_frame = None
        self._latest_capture_ts_ns = 0
        self._latest_frame_seq = 0
        self._processed_frame_seq = 0
        self._capture_error_count = 0
        self._dynamic_exposure_frame_counter = 0
        self._empty_hands_data = HandsData({}, {})

        # Timestamp monotonicity for detect_for_video
        self._last_video_timestamp_ms = 0

        # Rolling pipeline metrics
        self._pipeline_frame_times_ms = deque(maxlen=self.metrics_window)
        self._callback_intervals_ns = deque(maxlen=self.metrics_window)
        self._last_loop_end_ns = None
        self._capture_times_ms = deque(maxlen=self.metrics_window)
        self._capture_lag_times_ms = deque(maxlen=self.metrics_window)
        self._preprocess_times_ms = deque(maxlen=self.metrics_window)
        self._inference_times_ms = deque(maxlen=self.metrics_window)
        self._hands_data_times_ms = deque(maxlen=self.metrics_window)
        self._strategize_times_ms = deque(maxlen=self.metrics_window)
        self._emit_times_ms = deque(maxlen=self.metrics_window)
        self._dropped_capture_frames = deque(maxlen=self.metrics_window)

        # Reusable RGB ring buffers to reduce per-frame allocation churn.
        self._rgb_buffers = []
        self._rgb_buffer_index = 0
        self._rgb_buffer_count = 6

        self._initialize_mediapipe()

    def _initialize_mediapipe(self):
        """Initialize MediaPipe Hand Landmarker in VIDEO mode."""
        try:
            BaseOptions = mp.tasks.BaseOptions
            HandLandmarker = mp.tasks.vision.HandLandmarker
            HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
            VisionRunningMode = mp.tasks.vision.RunningMode

            options = HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=self.model_path),
                running_mode=VisionRunningMode.VIDEO,
                num_hands=self.num_hands,
                min_hand_detection_confidence=self.min_detection_confidence,
                min_hand_presence_confidence=self.min_presence_confidence,
                min_tracking_confidence=self.min_tracking_confidence,
            )

            self.landmarker = HandLandmarker.create_from_options(options)
            print('MediaPipe Hand Landmarker initialized successfully (VIDEO)')

        except Exception as e:
            print(f'Error initializing MediaPipe: {e}')
            raise

    def _initialize_camera(self, camera_index=0, width=640, height=480):
        """Initialize the camera."""
        try:
            is_windows = platform.system() == "Windows"
            is_linux = platform.system() == "Linux"
            using_dshow = False
            using_v4l2 = False

            # On Windows prefer DirectShow to avoid MSMF instability/overhead where possible.
            if is_windows and hasattr(cv2, 'CAP_DSHOW'):
                self.cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
                using_dshow = bool(self.cap and self.cap.isOpened())
            elif is_linux and hasattr(cv2, 'CAP_V4L2'):
                # On Linux prefer V4L2 so UVC controls (auto-exposure, gain, etc.) are addressable.
                self.cap = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
                using_v4l2 = bool(self.cap and self.cap.isOpened())
            else:
                self.cap = cv2.VideoCapture(camera_index)

            if (not self.cap) or (not self.cap.isOpened()):
                self.cap = cv2.VideoCapture(camera_index)

            if not self.cap.isOpened():
                raise Exception('Could not open webcam')

            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

            # Best-effort low-latency buffer size (backend dependent)
            if hasattr(cv2, 'CAP_PROP_BUFFERSIZE') and self.camera_buffer_size > 0:
                self._set_camera_prop(cv2.CAP_PROP_BUFFERSIZE, self.camera_buffer_size)

            # Best-effort target camera fps.
            if hasattr(cv2, 'CAP_PROP_FPS') and self.camera_target_fps > 0:
                self._set_camera_prop(cv2.CAP_PROP_FPS, self.camera_target_fps)

            # Best-effort exposure controls (driver/backend dependent).
            if hasattr(cv2, 'CAP_PROP_AUTO_EXPOSURE'):
                self._set_auto_exposure(self.camera_auto_exposure)

            if (not self.camera_auto_exposure) and (self.camera_exposure_value is not None) and hasattr(cv2, 'CAP_PROP_EXPOSURE'):
                self._set_camera_prop(cv2.CAP_PROP_EXPOSURE, float(self.camera_exposure_value))

            if self.camera_gain_value is not None and hasattr(cv2, 'CAP_PROP_GAIN'):
                self._set_camera_prop(cv2.CAP_PROP_GAIN, float(self.camera_gain_value))

            # Best-effort webcam format tuning on desktop platforms.
            selected_format = None
            if (is_windows or is_linux) and hasattr(cv2, 'CAP_PROP_FOURCC'):
                preferred_fourccs = ("MJPG", "YUYV", "YUY2")
                for fourcc_text in preferred_fourccs:
                    fourcc = cv2.VideoWriter_fourcc(*fourcc_text)
                    self._set_camera_prop(cv2.CAP_PROP_FOURCC, fourcc)
                    reported = self._decode_fourcc(self.cap.get(cv2.CAP_PROP_FOURCC))
                    if reported == fourcc_text:
                        selected_format = reported
                        break

                if selected_format is None:
                    # Keep first preferred format even if backend doesn't report reliably.
                    self._set_camera_prop(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                    selected_format = self._decode_fourcc(self.cap.get(cv2.CAP_PROP_FOURCC))

            backend_name = self.cap.getBackendName() if hasattr(self.cap, 'getBackendName') else 'unknown'
            backend_upper = str(backend_name).upper()
            using_v4l2 = using_v4l2 or ('V4L' in backend_upper)
            self._camera_readback = {
                'backend': backend_name,
                'dshow': using_dshow,
                'v4l2': using_v4l2,
                'fourcc': selected_format or self._decode_fourcc(self._read_camera_prop(cv2.CAP_PROP_FOURCC)),
                'width': self._read_camera_prop(cv2.CAP_PROP_FRAME_WIDTH),
                'height': self._read_camera_prop(cv2.CAP_PROP_FRAME_HEIGHT),
                'fps': self._read_camera_prop(cv2.CAP_PROP_FPS),
                'auto_exposure': self._read_camera_prop(cv2.CAP_PROP_AUTO_EXPOSURE),
                'exposure': self._read_camera_prop(cv2.CAP_PROP_EXPOSURE),
                'gain': self._read_camera_prop(cv2.CAP_PROP_GAIN),
            }

            if self.camera_readback_log:
                width_readback = self._camera_readback.get('width')
                height_readback = self._camera_readback.get('height')
                fps_readback = self._camera_readback.get('fps')
                width_text = str(int(width_readback)) if width_readback is not None else '?'
                height_text = str(int(height_readback)) if height_readback is not None else '?'
                fps_text = f"{fps_readback:.2f}" if fps_readback is not None else '?'
                print(
                    'Camera initialized - '
                    f"res={width_text}x{height_text}, "
                    f"backend={self._camera_readback['backend']}, dshow={self._camera_readback['dshow']}, "
                    f"v4l2={self._camera_readback['v4l2']}, "
                    f"fourcc={self._camera_readback['fourcc'] or 'default'}, "
                    f"fps={fps_text}, auto_exp={self._camera_readback['auto_exposure']}, "
                    f"exp={self._camera_readback['exposure']}, gain={self._camera_readback['gain']}"
                )
            else:
                print(
                    f'Camera initialized - Resolution: {width}x{height}, '
                    f'backend={backend_name}, dshow={using_dshow}, v4l2={using_v4l2}, '
                    f'fourcc={selected_format or "default"}'
                )

        except Exception as e:
            print(f'Error initializing camera: {e}')
            raise

    def _set_auto_exposure(self, enabled: bool):
        """Best-effort auto exposure toggle across drivers/backends."""
        if not hasattr(cv2, 'CAP_PROP_AUTO_EXPOSURE'):
            return

        backend_name = ''
        if self.cap is not None and hasattr(self.cap, 'getBackendName'):
            try:
                backend_name = self.cap.getBackendName()
            except Exception:
                backend_name = ''
        backend_upper = str(backend_name).upper()

        # Common backend conventions:
        # - V4L2 (Linux): 3 auto, 1 manual
        # - Existing cross-platform behavior in this project: 0.75 auto, 0.25 manual
        if ('V4L' in backend_upper) or (platform.system() == "Linux"):
            candidates = (3.0,) if enabled else (1.0,)
        else:
            candidates = (0.75, 1.0) if enabled else (0.25, 0.0)

        for value in candidates:
            self._set_camera_prop(cv2.CAP_PROP_AUTO_EXPOSURE, value)

    def _set_camera_prop(self, prop_id, value):
        """Set a camera property best-effort."""
        try:
            return bool(self.cap.set(prop_id, value))
        except Exception:
            return False

    def _read_camera_prop(self, prop_id):
        """Read a camera property best-effort."""
        try:
            if self.cap is None:
                return None
            value = self.cap.get(prop_id)
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _decode_fourcc(fourcc_value):
        """Decode OpenCV FOURCC numeric value into a 4-char string."""
        if fourcc_value is None:
            return None
        try:
            value = int(fourcc_value)
            chars = [chr((value >> (8 * i)) & 0xFF) for i in range(4)]
            decoded = ''.join(chars).replace('\x00', '')
            return decoded or None
        except Exception:
            return None

    def set_preview_enabled(self, enabled: bool):
        """Enable or disable preview frame emission to the UI."""
        self.preview_enabled = enabled

    def _next_video_timestamp_ms(self, capture_ts_ns):
        """Get monotonic millisecond timestamp for detect_for_video."""
        timestamp_ms = capture_ts_ns // 1_000_000
        if timestamp_ms <= self._last_video_timestamp_ms:
            timestamp_ms = self._last_video_timestamp_ms + 1
        self._last_video_timestamp_ms = timestamp_ms
        return int(timestamp_ms)

    def _compute_pipeline_fps(self):
        """Compute rolling loop FPS from inter-loop intervals."""
        if not self._callback_intervals_ns:
            return 0.0

        avg_interval_ns = sum(self._callback_intervals_ns) / len(self._callback_intervals_ns)
        if avg_interval_ns <= 0:
            return 0.0

        return 1_000_000_000.0 / avg_interval_ns

    def _compute_avg_pipeline_ms(self):
        """Compute rolling average pipeline duration in ms."""
        if not self._pipeline_frame_times_ms:
            return 0.0

        return sum(self._pipeline_frame_times_ms) / len(self._pipeline_frame_times_ms)

    @staticmethod
    def _avg(values):
        """Compute average of a deque/list, falling back to 0.0 when empty."""
        if not values:
            return 0.0
        return sum(values) / len(values)

    def _ensure_rgb_buffers(self, frame_shape):
        """Allocate/reallocate reusable RGB buffers when camera shape changes."""
        if len(frame_shape) != 3:
            return

        height, width, channels = frame_shape
        if channels != 3:
            return

        needs_realloc = False
        if len(self._rgb_buffers) != self._rgb_buffer_count:
            needs_realloc = True
        else:
            for buf in self._rgb_buffers:
                if buf.shape != frame_shape or buf.dtype != np.uint8:
                    needs_realloc = True
                    break

        if needs_realloc:
            self._rgb_buffers = [
                np.empty((height, width, channels), dtype=np.uint8)
                for _ in range(self._rgb_buffer_count)
            ]
            self._rgb_buffer_index = 0

    def _next_rgb_buffer(self):
        """Get next reusable RGB buffer in ring."""
        if not self._rgb_buffers:
            return None
        buf = self._rgb_buffers[self._rgb_buffer_index]
        self._rgb_buffer_index = (self._rgb_buffer_index + 1) % self._rgb_buffer_count
        return buf

    def _reset_frame_slot(self):
        """Reset latest-frame slot used by decoupled capture/inference mode."""
        with self._frame_condition:
            self._latest_frame = None
            self._latest_capture_ts_ns = 0
            self._latest_frame_seq = 0
            self._processed_frame_seq = 0

    def _start_capture_thread(self):
        """Start dedicated camera capture thread for latest-frame-only processing."""
        self._stop_capture_thread()
        self._capture_thread = Thread(target=self._capture_worker, name="camera-capture", daemon=True)
        self._capture_thread.start()

    def _stop_capture_thread(self):
        """Stop capture thread if running."""
        thread = self._capture_thread
        self._capture_thread = None
        if thread and thread.is_alive():
            thread.join(timeout=0.5)

    def _capture_worker(self):
        """Read camera frames continuously and keep only the newest frame."""
        while self.is_running and self.cap is not None:
            ret, frame = self.cap.read()
            capture_ts_ns = time.perf_counter_ns()

            if not self.is_running:
                break

            if not ret:
                self._capture_error_count += 1
                time.sleep(0.002)
                continue

            self._maybe_adjust_dynamic_exposure(frame)

            with self._frame_condition:
                self._latest_frame = frame
                self._latest_capture_ts_ns = capture_ts_ns
                self._latest_frame_seq += 1
                self._frame_condition.notify()

    def _wait_for_next_frame(self, timeout_sec=0.25):
        """
        Wait for a fresh frame from capture thread.

        Returns:
            tuple: (frame, capture_ts_ns, dropped_frames, wait_ms)
        """
        wait_start_ns = time.perf_counter_ns()
        frame = None
        capture_ts_ns = 0
        dropped_frames = 0

        with self._frame_condition:
            prev_seq = self._processed_frame_seq
            while self.is_running and self._latest_frame_seq <= prev_seq:
                self._frame_condition.wait(timeout=timeout_sec)
                if self._latest_frame_seq <= prev_seq:
                    break

            if self.is_running and self._latest_frame_seq > prev_seq:
                frame = self._latest_frame
                capture_ts_ns = self._latest_capture_ts_ns
                current_seq = self._latest_frame_seq
                dropped_frames = max(0, current_seq - prev_seq - 1)
                self._processed_frame_seq = current_seq

        wait_ms = (time.perf_counter_ns() - wait_start_ns) / 1_000_000.0
        return frame, capture_ts_ns, dropped_frames, wait_ms

    @staticmethod
    def _sample_frame_luma(frame):
        """
        Estimate frame brightness quickly using subsampled green channel.

        Green carries most luma contribution and avoids an extra color conversion.
        """
        if frame is None or frame.size == 0 or frame.ndim != 3:
            return None
        sample = frame[::8, ::8, 1]
        if sample.size == 0:
            return None
        return float(sample.mean())

    def _maybe_adjust_dynamic_exposure(self, frame):
        """Adjust manual exposure periodically to keep brightness near target."""
        if self.camera_auto_exposure:
            return
        if not self.camera_dynamic_exposure:
            return
        if not hasattr(cv2, 'CAP_PROP_EXPOSURE'):
            return

        self._dynamic_exposure_frame_counter += 1
        every_n = max(1, self.camera_dynamic_exposure_every_n_frames)
        if (self._dynamic_exposure_frame_counter % every_n) != 0:
            return

        luma = self._sample_frame_luma(frame)
        if luma is None:
            return

        target = self.camera_dynamic_exposure_target_luma
        tolerance = max(0.0, self.camera_dynamic_exposure_tolerance_luma)
        low = target - tolerance
        high = target + tolerance
        if low <= luma <= high:
            return

        current = self._read_camera_prop(cv2.CAP_PROP_EXPOSURE)
        if current is None:
            return

        step = abs(self.camera_dynamic_exposure_step)
        if step <= 0:
            return

        if luma < low:
            candidate = current + step
        else:
            candidate = current - step

        if self.camera_dynamic_exposure_min is not None:
            candidate = max(float(self.camera_dynamic_exposure_min), candidate)
        if self.camera_dynamic_exposure_max is not None:
            candidate = min(float(self.camera_dynamic_exposure_max), candidate)

        if abs(candidate - current) < 1e-6:
            return

        self._set_camera_prop(cv2.CAP_PROP_EXPOSURE, candidate)
        self._camera_readback['exposure'] = candidate

    def start_tracking(self, camera_index=0, width=640, height=480):
        """
        Start hand tracking in background thread.

        Args:
            camera_index: Camera index (0 for default camera)
            width: Camera width resolution
            height: Camera height resolution

        Returns:
            bool: True if tracking started successfully
        """
        if self.isRunning():
            print('Tracking is already running')
            return False

        self.camera_index = camera_index
        self.camera_width = width
        self.camera_height = height
        self.start()
        return True

    def run(self):
        """Main tracking loop (runs in background thread)."""
        try:
            self._initialize_camera(self.camera_index, self.camera_width, self.camera_height)

            self._pipeline_frame_times_ms.clear()
            self._callback_intervals_ns.clear()
            self._last_loop_end_ns = None
            self._last_video_timestamp_ms = 0
            self._rgb_buffers = []
            self._rgb_buffer_index = 0
            self._capture_times_ms.clear()
            self._capture_lag_times_ms.clear()
            self._preprocess_times_ms.clear()
            self._inference_times_ms.clear()
            self._hands_data_times_ms.clear()
            self._strategize_times_ms.clear()
            self._emit_times_ms.clear()
            self._dropped_capture_frames.clear()
            self._capture_error_count = 0
            self._dynamic_exposure_frame_counter = 0
            self._reset_frame_slot()

            self.is_running = True
            self._stopped_emitted = False
            print('Hand tracking started in background thread')
            self.tracking_started.emit()

            # Allow camera auto-exposure to settle and drop stale startup frames.
            for _ in range(max(0, self.camera_warmup_frames)):
                if not self.is_running:
                    break
                self.cap.read()

            if self.capture_latest_frame_only:
                self._start_capture_thread()

            frame_budget_ns = 0
            if self.target_max_fps > 0:
                frame_budget_ns = int(1_000_000_000 / self.target_max_fps)

            while self.is_running:
                loop_start_ns = time.perf_counter_ns()

                # Capture
                dropped_frames = 0
                capture_lag_ms = 0.0
                if self.capture_latest_frame_only:
                    frame, capture_ts_ns, dropped_frames, capture_ms = self._wait_for_next_frame()
                    if frame is None:
                        continue
                    capture_done_ns = time.perf_counter_ns()
                    capture_lag_ms = max(0.0, (loop_start_ns - capture_ts_ns) / 1_000_000.0)
                else:
                    ret, frame = self.cap.read()
                    capture_done_ns = time.perf_counter_ns()
                    if not ret:
                        print('Error: Could not read frame from webcam')
                        break
                    self._maybe_adjust_dynamic_exposure(frame)
                    capture_ts_ns = capture_done_ns
                    capture_ms = (capture_done_ns - loop_start_ns) / 1_000_000.0

                self.action.set_frame_capture_ts_ns(capture_ts_ns)

                # Preprocess for MediaPipe
                preprocess_start_ns = time.perf_counter_ns()
                self._ensure_rgb_buffers(frame.shape)
                rgb_frame = self._next_rgb_buffer()
                if rgb_frame is None:
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                else:
                    cv2.cvtColor(frame, cv2.COLOR_BGR2RGB, dst=rgb_frame)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                preprocess_done_ns = time.perf_counter_ns()

                # Inference
                infer_start_ns = time.perf_counter_ns()
                timestamp_ms = self._next_video_timestamp_ms(capture_ts_ns)
                detection_result = self.landmarker.detect_for_video(mp_image, timestamp_ms)
                infer_done_ns = time.perf_counter_ns()

                # Postprocess + strategize
                hands_data = None
                hands_data_ms = 0.0
                strategize_ms = 0.0

                if detection_result and detection_result.hand_landmarks:
                    hands_data_start_ns = time.perf_counter_ns()
                    hands_data = HandsData.from_detection_result(
                        detection_result,
                        right_hand_only=self.right_hand_only_processing,
                    )
                    hands_data_end_ns = time.perf_counter_ns()
                    hands_data_ms = (hands_data_end_ns - hands_data_start_ns) / 1_000_000.0

                    should_strategize = True
                    if self.right_hand_only_processing and not hands_data.wrist.has_right:
                        hands_data = self._empty_hands_data
                        should_strategize = False

                    if should_strategize:
                        strategize_start_ns = time.perf_counter_ns()
                        self.strategizer.strategize(hands_data, frame_capture_ts_ns=capture_ts_ns)
                        strategize_end_ns = time.perf_counter_ns()
                        strategize_ms = (strategize_end_ns - strategize_start_ns) / 1_000_000.0
                else:
                    # Reuse explicit empty state and skip strategizer when no hands are present.
                    hands_data = self._empty_hands_data

                loop_end_ns = time.perf_counter_ns()

                # Update rolling metrics
                pipeline_ms = (loop_end_ns - loop_start_ns) / 1_000_000.0
                self._pipeline_frame_times_ms.append(pipeline_ms)

                if self._last_loop_end_ns is not None:
                    interval_ns = loop_end_ns - self._last_loop_end_ns
                    if interval_ns > 0:
                        self._callback_intervals_ns.append(interval_ns)
                self._last_loop_end_ns = loop_end_ns

                preprocess_ms = (preprocess_done_ns - preprocess_start_ns) / 1_000_000.0
                inference_ms = (infer_done_ns - infer_start_ns) / 1_000_000.0
                self._capture_times_ms.append(capture_ms)
                self._capture_lag_times_ms.append(capture_lag_ms)
                self._preprocess_times_ms.append(preprocess_ms)
                self._inference_times_ms.append(inference_ms)
                self._hands_data_times_ms.append(hands_data_ms)
                self._strategize_times_ms.append(strategize_ms)
                self._dropped_capture_frames.append(float(dropped_frames))

                pipeline_fps = self._compute_pipeline_fps()
                frame_pipeline_ms_avg = self._compute_avg_pipeline_ms()

                action_latency = self.action.get_latency_stats()

                landmarks_data = {
                    'smoothed_hands_data': hands_data,
                    'metrics': {
                        'pipeline_fps': pipeline_fps,
                        'action_latency_avg_ms': action_latency['avg_ms'],
                        'action_latency_latest_ms': action_latency['latest_ms'],
                        'action_latency_p95_ms': action_latency['p95_ms'],
                        'frame_pipeline_ms_avg': frame_pipeline_ms_avg,
                        'capture_ms': self._avg(self._capture_times_ms),
                        'capture_queue_lag_ms': self._avg(self._capture_lag_times_ms),
                        'preprocess_ms': self._avg(self._preprocess_times_ms),
                        'inference_wait_ms': self._avg(self._inference_times_ms),
                        'hands_data_ms': self._avg(self._hands_data_times_ms),
                        'strategize_ms': self._avg(self._strategize_times_ms),
                        'emit_ms': self._avg(self._emit_times_ms),
                        'dropped_pending_frames': self._avg(self._dropped_capture_frames),
                        'camera_backend': self._camera_readback.get('backend'),
                        'camera_fourcc': self._camera_readback.get('fourcc'),
                        'camera_fps_readback': self._camera_readback.get('fps'),
                        'camera_exposure_readback': self._camera_readback.get('exposure'),
                        'camera_gain_readback': self._camera_readback.get('gain'),
                        'capture_read_errors': self._capture_error_count,
                    },
                }

                # Reuse converted RGB frame; ring buffers avoid extra copy while preventing overwrite races.
                emit_start_ns = time.perf_counter_ns()
                emit_frame = rgb_frame if self.preview_enabled else None
                self.landmarks_detected.emit(landmarks_data, emit_frame)
                emit_end_ns = time.perf_counter_ns()
                self._emit_times_ms.append((emit_end_ns - emit_start_ns) / 1_000_000.0)

                # FPS cap behavior (no delay if already below cap)
                if frame_budget_ns > 0:
                    elapsed_ns = time.perf_counter_ns() - loop_start_ns
                    if elapsed_ns < frame_budget_ns:
                        time.sleep((frame_budget_ns - elapsed_ns) / 1_000_000_000.0)

        except KeyboardInterrupt:
            print('\nInterrupted by user')
            self.error_occurred.emit('Interrupted by user')
        except Exception as e:
            error_msg = f'Error occurred: {e}'
            print(error_msg)
            self.error_occurred.emit(error_msg)
        finally:
            self._cleanup()

    def stop_tracking(self):
        """Stop hand tracking and wait for thread exit."""
        print('Stopping hand tracking...')
        self.is_running = False
        with self._frame_condition:
            self._frame_condition.notify_all()

        if self.isRunning():
            self.wait(2000)
        else:
            self._cleanup()

    def _cleanup(self):
        """Internal cleanup method."""
        self.is_running = False
        with self._frame_condition:
            self._frame_condition.notify_all()
        self._stop_capture_thread()

        if hasattr(self.action, "release_all_keys"):
            self.action.release_all_keys()

        if self.cap:
            self.cap.release()
            self.cap = None
            print('Camera released')

        self._rgb_buffers = []
        self._rgb_buffer_index = 0
        self._camera_readback = {}
        self._reset_frame_slot()

        if not self._stopped_emitted:
            self._stopped_emitted = True
            print('Hand tracking stopped')
            self.tracking_stopped.emit()
