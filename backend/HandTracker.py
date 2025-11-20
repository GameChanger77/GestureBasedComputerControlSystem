import cv2
import mediapipe as mp
import numpy as np
import os
import time

from PySide6.QtCore import QThread, Signal

from backend.HandsData import HandsData
from backend.LandmarkSmoother import LandmarkSmoother


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
        self.wrist_smoother = LandmarkSmoother()
        self.camera_smoother = LandmarkSmoother()
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

        # Hand landmark connections (based on MediaPipe hand model)
        self.HAND_CONNECTIONS = [
            # Thumb
            (0, 1), (1, 2), (2, 3), (3, 4),
            # Index finger
            (0, 5), (5, 6), (6, 7), (7, 8),
            # Middle finger
            (0, 9), (9, 10), (10, 11), (11, 12),
            # Ring finger
            (0, 13), (13, 14), (14, 15), (15, 16),
            # Pinky
            (0, 17), (17, 18), (18, 19), (19, 20)
        ]

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

    def get_hands_data(self, detection_result, normalize=True):
        """
        Convert detection result to easily accessible hand data organized by finger

        Args:
            detection_result: MediaPipe detection result
            normalize (bool): If True, normalize coordinates relative to wrist and hand size

        Returns:
            HandsData: Object with dot notation access like:
                       data.wrist.left.wrist  # wrist position
                       data.wrist.left.thumb[3]  # thumb tip
                       data.wrist.left.tip['index']  # index fingertip shortcut
        """
        wrist_data = {}
        camera_data = {}

        if detection_result.hand_landmarks and detection_result.handedness:
            for i, (hand_landmarks, handedness) in enumerate(
                    zip(detection_result.hand_landmarks, detection_result.handedness)):

                # Get hand label (Left or Right)
                hand_label = handedness[0].category_name

                # Convert all landmarks to list of (x,y,z) tuples
                all_landmarks = []
                for landmark in hand_landmarks:
                    all_landmarks.append((landmark.x, landmark.y, landmark.z))

                # Store camera-relative data (wrist + 4 joints per finger)
                camera_fingers = [
                    [all_landmarks[0], all_landmarks[1], all_landmarks[2],
                     all_landmarks[3], all_landmarks[4]],  # Wrist + Thumb
                    [all_landmarks[0], all_landmarks[5], all_landmarks[6],
                     all_landmarks[7], all_landmarks[8]],  # Wrist + Index
                    [all_landmarks[0], all_landmarks[9], all_landmarks[10],
                     all_landmarks[11], all_landmarks[12]],  # Wrist + Middle
                    [all_landmarks[0], all_landmarks[13], all_landmarks[14],
                     all_landmarks[15], all_landmarks[16]],  # Wrist + Ring
                    [all_landmarks[0], all_landmarks[17], all_landmarks[18],
                     all_landmarks[19], all_landmarks[20]]  # Wrist + Pinky
                ]
                camera_data[hand_label] = camera_fingers

                if normalize:
                    # Normalize coordinates relative to wrist and hand size
                    wrist = np.array(all_landmarks[0])

                    # Calculate hand size (distance from wrist to middle finger MCP joint)
                    middle_mcp = np.array(all_landmarks[9])
                    hand_size = np.linalg.norm(middle_mcp - wrist)

                    # Avoid division by zero
                    if hand_size < 1e-6:
                        hand_size = 1.0

                    # Vectorized normalization (process all landmarks at once)
                    landmarks_array = np.array(all_landmarks)
                    normalized_array = (landmarks_array - wrist) / hand_size
                    all_landmarks = [tuple(pos) for pos in normalized_array]

                # Organize normalized landmarks by finger (wrist + 4 joints per finger)
                wrist_fingers = [
                    [all_landmarks[0], all_landmarks[1], all_landmarks[2],
                     all_landmarks[3], all_landmarks[4]],  # Wrist + Thumb
                    [all_landmarks[0], all_landmarks[5], all_landmarks[6],
                     all_landmarks[7], all_landmarks[8]],  # Wrist + Index
                    [all_landmarks[0], all_landmarks[9], all_landmarks[10],
                     all_landmarks[11], all_landmarks[12]],  # Wrist + Middle
                    [all_landmarks[0], all_landmarks[13], all_landmarks[14],
                     all_landmarks[15], all_landmarks[16]],  # Wrist + Ring
                    [all_landmarks[0], all_landmarks[17], all_landmarks[18],
                     all_landmarks[19], all_landmarks[20]]  # Wrist + Pinky
                ]
                wrist_data[hand_label] = wrist_fingers

        # Create HandsData object and smooth it
        hands_data = HandsData(wrist_data, camera_data)
        hands_data = self.wrist_smoother.smooth_hands_data(hands_data)
        hands_data = self.camera_smoother.smooth_hands_data(hands_data)

        return hands_data

    def draw_landmarks(self, image, detection_result):
        """
        Draw hand landmarks and connections on the image

        Args:
            image: OpenCV image array
            detection_result: MediaPipe detection result

        Returns:
            Annotated image with landmarks drawn
        """
        if detection_result.hand_landmarks:
            for hand_landmarks in detection_result.hand_landmarks:
                # Convert normalized coordinates to pixel coordinates
                height, width, _ = image.shape
                landmark_points = []

                for landmark in hand_landmarks:
                    x = int(landmark.x * width)
                    y = int(landmark.y * height)
                    landmark_points.append((x, y))

                # Draw connections
                for connection in self.HAND_CONNECTIONS:
                    start_idx, end_idx = connection
                    if start_idx < len(landmark_points) and end_idx < len(landmark_points):
                        cv2.line(image, landmark_points[start_idx], landmark_points[end_idx],
                                 (0, 255, 0), 2)

                # Draw landmark points
                for i, point in enumerate(landmark_points):
                    # Different colors for different finger parts
                    if i == 0:  # Wrist
                        color = (255, 0, 0)  # Red
                        radius = 8
                    elif i in [4, 8, 12, 16, 20]:  # Fingertips
                        color = (0, 0, 255)  # Blue
                        radius = 6
                    else:  # Other joints
                        color = (255, 255, 0)  # Cyan
                        radius = 4

                    cv2.circle(image, point, radius, color, -1)

                    # Optional: Add landmark numbers (disabled for performance - saves 8-12ms)
                    cv2.putText(image, str(i), (point[0] + 10, point[1] - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255), 1)

        # Add instructions text
        cv2.putText(image, "Press 'q' to quit", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Add hand count info
        hand_count = len(detection_result.hand_landmarks) if detection_result.hand_landmarks else 0
        cv2.putText(image, f"Hands detected: {hand_count}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Add FPS display
        cv2.putText(image, f"FPS: {self.fps:.1f}", (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        return image

    def process_frame(self, frame):
        """
        Process a single frame for hand detection

        Args:
            frame: OpenCV frame from camera

        Returns:
            tuple: (annotated_frame, detection_result)
        """
        # Flip frame horizontally for mirror effect
        # frame = cv2.flip(frame, 1)

        # Convert BGR to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Create MediaPipe Image
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        # Perform hand landmark detection
        timestamp_ms = int(cv2.getTickCount() / cv2.getTickFrequency() * 1000)
        detection_result = self.landmarker.detect_for_video(mp_image, timestamp_ms)

        # Call strategize method if landmarks are detected
        if detection_result.hand_landmarks:
            self.strategizer.strategize(self.get_hands_data(detection_result))

        return detection_result

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
                detection_result = self.process_frame(frame)

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

                # Emit signal with landmarks and frame data (thread-safe)
                landmarks_data = {
                    'detection_result': detection_result,
                    'fps': self.fps
                }
                self.landmarks_detected.emit(landmarks_data, frame.copy())

                frame_count += 1

                # Optional: Add frame rate limiting or other processing here

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
