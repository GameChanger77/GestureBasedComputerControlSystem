import cv2
import mediapipe as mp
import os
import time

from PySide6.QtCore import QThread, Signal

from backend.HandsData import HandsData


class HandTracker(QThread):
    # Qt signals for thread-safe communication
    landmarks_detected = Signal(dict, object)  # landmarks_data, frame
    tracking_started = Signal()
    tracking_stopped = Signal()
    error_occurred = Signal(str)

    def __init__(self, strategizer, action, model_path=os.path.join('.', 'backend', 'models', 'hand_landmarker.task'),
                 num_hands=2):
        """
        Initialize the Hand Landmark Detector

        Args:
            model_path (str): Path to the hand landmarker model file
            num_hands (int): Maximum number of hands to detect
        """
        super().__init__()  # Initialize QThread
        self.strategizer = strategizer
        self.action = action
        self.model_path = model_path
        self.num_hands = num_hands

        # Camera configuration (set when tracking starts)
        self.camera_index = 0
        self.camera_width = 640
        self.camera_height = 480

        # Detection parameters
        self.min_detection_confidence = 0.5
        self.min_presence_confidence = 0.5
        self.min_tracking_confidence = 0.5

        # Initialize components
        self.landmarker = None
        self.cap = None
        self.is_running = False

        # FPS tracking
        self.fps = 0
        self.frame_times = []
        self.last_fps_update = time.time()

        self._initialize_mediapipe()

    def _initialize_mediapipe(self):
        """Initialize MediaPipe Hand Landmarker"""
        try:
            # MediaPipe setup
            BaseOptions = mp.tasks.BaseOptions
            HandLandmarker = mp.tasks.vision.HandLandmarker
            HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
            VisionRunningMode = mp.tasks.vision.RunningMode

            # Configure the hand landmarker
            options = HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=self.model_path),
                running_mode=VisionRunningMode.VIDEO,
                num_hands=self.num_hands,
                min_hand_detection_confidence=self.min_detection_confidence,
                min_hand_presence_confidence=self.min_presence_confidence,
                min_tracking_confidence=self.min_tracking_confidence
            )

            # Create the hand landmarker
            self.landmarker = HandLandmarker.create_from_options(options)
            print("MediaPipe Hand Landmarker initialized successfully")

        except Exception as e:
            print(f"Error initializing MediaPipe: {e}")
            raise

    def _initialize_camera(self, camera_index=0, width=640, height=480):
        """Initialize the camera"""
        try:
            self.cap = cv2.VideoCapture(camera_index)

            if not self.cap.isOpened():
                raise Exception("Could not open webcam")

            # Set camera properties
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

            print(f"Camera initialized - Resolution: {width}x{height}")

        except Exception as e:
            print(f"Error initializing camera: {e}")
            raise

    def process_frame(self, frame):
        """
        Process a single frame for hand detection

        Args:
            frame: OpenCV frame from camera

        Returns:
            tuple: (detection_result, smoothed_hands_data)
        """
        # Convert BGR to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Create MediaPipe Image
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        # Perform hand landmark detection
        timestamp_ms = int(cv2.getTickCount() / cv2.getTickFrequency() * 1000)
        detection_result = self.landmarker.detect_for_video(mp_image, timestamp_ms)

        # Get smoothed hands data
        hands_data = None
        if detection_result.hand_landmarks:
            hands_data = HandsData.from_detection_result(detection_result)
            self.strategizer.strategize(hands_data)

        return detection_result, hands_data

    def start_tracking(self, camera_index=0, width=640, height=480):
        """
        Start hand tracking in background thread.

        Args:
            camera_index (int): Camera index (0 for default camera)
            width (int): Camera width resolution
            height (int): Camera height resolution

        Returns:
            bool: True if tracking started successfully, False otherwise
        """
        if self.isRunning():
            print("Tracking is already running")
            return False

        # Store camera configuration
        self.camera_index = camera_index
        self.camera_width = width
        self.camera_height = height

        # Start the thread (calls run() in background)
        self.start()
        return True

    def run(self):
        """
        Main tracking loop (runs in background thread).
        Called automatically by QThread.start().
        """
        try:
            # Initialize camera
            self._initialize_camera(self.camera_index, self.camera_width, self.camera_height)

            self.is_running = True
            print("Hand tracking started in background thread")
            self.tracking_started.emit()

            frame_count = 0

            while self.is_running:
                # Track frame start time
                frame_start = time.time()

                # Read frame from webcam
                ret, frame = self.cap.read()
                if not ret:
                    print("Error: Could not read frame from webcam")
                    break

                # Process the frame
                detection_result, smoothed_hands_data = self.process_frame(frame)

                # Calculate FPS
                frame_time = time.time() - frame_start
                self.frame_times.append(frame_time)

                # Update FPS every second
                if time.time() - self.last_fps_update >= 1.0:
                    if len(self.frame_times) > 0:
                        avg_frame_time = sum(self.frame_times) / len(self.frame_times)
                        self.fps = 1.0 / avg_frame_time if avg_frame_time > 0 else 0
                        self.frame_times = []
                        self.last_fps_update = time.time()

                # Emit signal with smoothed landmarks and frame data (thread-safe)
                landmarks_data = {
                    'detection_result': detection_result,
                    'smoothed_hands_data': smoothed_hands_data,
                    'fps': self.fps
                }
                self.landmarks_detected.emit(landmarks_data, frame.copy())

                frame_count += 1

                # Add frame rate limiting here if we want it

        except KeyboardInterrupt:
            print("\nInterrupted by user")
            self.error_occurred.emit("Interrupted by user")
        except Exception as e:
            error_msg = f"Error occurred: {e}"
            print(error_msg)
            self.error_occurred.emit(error_msg)
        finally:
            self._cleanup()

    def stop_tracking(self):
        """Stop hand tracking and cleanup resources"""
        print("Stopping hand tracking...")
        self.is_running = False

        # Wait for thread to finish (up to 2 seconds)
        if self.isRunning():
            self.wait(2000)

        self._cleanup()

    def _cleanup(self):
        """Internal cleanup method"""
        if self.cap:
            self.cap.release()
            print("Camera released")

        print("Hand tracking stopped")
        self.tracking_stopped.emit()
