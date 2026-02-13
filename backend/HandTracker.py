import cv2
import mediapipe as mp
import os
import platform
import time
from collections import deque
import numpy as np

from PySide6.QtCore import QThread, Signal

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
        model_path=os.path.join('.', 'backend', 'models', 'hand_landmarker.task'),
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
        self.camera_exposure_value = config.get('camera_exposure_value', None) if config else None
        self.camera_gain_value = config.get('camera_gain_value', None) if config else None
        self.camera_warmup_frames = int(config.get('camera_warmup_frames', 8)) if config else 8
        self.camera_readback_log = bool(config.get('camera_readback_log', True)) if config else True

        # Runtime state
        self.landmarker = None
        self.cap = None
        self.is_running = False
        self.preview_enabled = True
        self._stopped_emitted = False
        self._camera_readback = {}

        # Timestamp monotonicity for detect_for_video
        self._last_video_timestamp_ms = 0

        # Rolling pipeline metrics
        self._pipeline_frame_times_ms = deque(maxlen=self.metrics_window)
        self._callback_intervals_ns = deque(maxlen=self.metrics_window)
        self._last_loop_end_ns = None

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
            using_dshow = False

            # On Windows prefer DirectShow to avoid MSMF instability/overhead where possible.
            if is_windows and hasattr(cv2, 'CAP_DSHOW'):
                self.cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
                using_dshow = bool(self.cap and self.cap.isOpened())
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
            if is_windows and hasattr(cv2, 'CAP_PROP_AUTO_EXPOSURE'):
                self._set_auto_exposure(self.camera_auto_exposure)

            if (not self.camera_auto_exposure) and (self.camera_exposure_value is not None) and hasattr(cv2, 'CAP_PROP_EXPOSURE'):
                self._set_camera_prop(cv2.CAP_PROP_EXPOSURE, float(self.camera_exposure_value))

            if self.camera_gain_value is not None and hasattr(cv2, 'CAP_PROP_GAIN'):
                self._set_camera_prop(cv2.CAP_PROP_GAIN, float(self.camera_gain_value))

            # Best-effort webcam format tuning on Windows.
            selected_format = None
            if is_windows and hasattr(cv2, 'CAP_PROP_FOURCC'):
                for fourcc_text in ("MJPG", "YUY2"):
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
            self._camera_readback = {
                'backend': backend_name,
                'dshow': using_dshow,
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
                    f"fourcc={self._camera_readback['fourcc'] or 'default'}, "
                    f"fps={fps_text}, auto_exp={self._camera_readback['auto_exposure']}, "
                    f"exp={self._camera_readback['exposure']}, gain={self._camera_readback['gain']}"
                )
            else:
                print(
                    f'Camera initialized - Resolution: {width}x{height}, '
                    f'backend={backend_name}, dshow={using_dshow}, fourcc={selected_format or "default"}'
                )

        except Exception as e:
            print(f'Error initializing camera: {e}')
            raise

    def _set_auto_exposure(self, enabled: bool):
        """Best-effort auto exposure toggle across drivers/backends."""
        if not hasattr(cv2, 'CAP_PROP_AUTO_EXPOSURE'):
            return

        # Common backend conventions:
        # - DSHOW: 0.75 auto, 0.25 manual
        # - Other drivers: 1 auto, 0 manual
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
        """Main synchronous tracking loop (runs in background thread)."""
        try:
            self._initialize_camera(self.camera_index, self.camera_width, self.camera_height)

            self._pipeline_frame_times_ms.clear()
            self._callback_intervals_ns.clear()
            self._last_loop_end_ns = None
            self._last_video_timestamp_ms = 0
            self._rgb_buffers = []
            self._rgb_buffer_index = 0

            self.is_running = True
            self._stopped_emitted = False
            print('Hand tracking started in background thread')
            self.tracking_started.emit()

            # Allow camera auto-exposure to settle and drop stale startup frames.
            for _ in range(max(0, self.camera_warmup_frames)):
                if not self.is_running:
                    break
                self.cap.read()

            frame_budget_ns = 0
            if self.target_max_fps > 0:
                frame_budget_ns = int(1_000_000_000 / self.target_max_fps)

            while self.is_running:
                loop_start_ns = time.perf_counter_ns()

                # Capture
                ret, frame = self.cap.read()
                capture_done_ns = time.perf_counter_ns()

                if not ret:
                    print('Error: Could not read frame from webcam')
                    break

                capture_ts_ns = capture_done_ns
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
                    hands_data = HandsData.from_detection_result(detection_result)
                    hands_data_end_ns = time.perf_counter_ns()
                    hands_data_ms = (hands_data_end_ns - hands_data_start_ns) / 1_000_000.0

                    strategize_start_ns = time.perf_counter_ns()
                    self.strategizer.strategize(hands_data, frame_capture_ts_ns=capture_ts_ns)
                    strategize_end_ns = time.perf_counter_ns()
                    strategize_ms = (strategize_end_ns - strategize_start_ns) / 1_000_000.0

                loop_end_ns = time.perf_counter_ns()

                # Update rolling metrics
                pipeline_ms = (loop_end_ns - loop_start_ns) / 1_000_000.0
                self._pipeline_frame_times_ms.append(pipeline_ms)

                if self._last_loop_end_ns is not None:
                    interval_ns = loop_end_ns - self._last_loop_end_ns
                    if interval_ns > 0:
                        self._callback_intervals_ns.append(interval_ns)
                self._last_loop_end_ns = loop_end_ns

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
                        'capture_ms': (capture_done_ns - loop_start_ns) / 1_000_000.0,
                        'preprocess_ms': (preprocess_done_ns - preprocess_start_ns) / 1_000_000.0,
                        'inference_wait_ms': (infer_done_ns - infer_start_ns) / 1_000_000.0,
                        'hands_data_ms': hands_data_ms,
                        'strategize_ms': strategize_ms,
                        'emit_ms': 0.0,
                        'dropped_pending_frames': 0,
                        'camera_backend': self._camera_readback.get('backend'),
                        'camera_fourcc': self._camera_readback.get('fourcc'),
                        'camera_fps_readback': self._camera_readback.get('fps'),
                        'camera_exposure_readback': self._camera_readback.get('exposure'),
                        'camera_gain_readback': self._camera_readback.get('gain'),
                    },
                }

                # Reuse converted RGB frame; ring buffers avoid extra copy while preventing overwrite races.
                emit_frame = rgb_frame if self.preview_enabled else None
                self.landmarks_detected.emit(landmarks_data, emit_frame)

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

        if self.isRunning():
            self.wait(2000)
        else:
            self._cleanup()

    def _cleanup(self):
        """Internal cleanup method."""
        if self.cap:
            self.cap.release()
            self.cap = None
            print('Camera released')

        self._rgb_buffers = []
        self._rgb_buffer_index = 0
        self._camera_readback = {}

        self.is_running = False

        if not self._stopped_emitted:
            self._stopped_emitted = True
            print('Hand tracking stopped')
            self.tracking_stopped.emit()
