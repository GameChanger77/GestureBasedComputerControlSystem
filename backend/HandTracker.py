import cv2
import mediapipe as mp
import numpy as np
import os


class HandTracker:
    def __init__(self, strategizer, action, smoother, model_path=os.path.join('.', 'backend', 'models', 'hand_landmarker.task'),
                 display_video=True, num_hands=2):
        """
        Initialize the Hand Landmark Detector

        Args:
            model_path (str): Path to the hand landmarker model file
            display_video (bool): Flag to show/hide video feed
            num_hands (int): Maximum number of hands to detect
        """
        self.strategizer = strategizer
        self.action = action
        self.model_path = model_path
        self.display_video = display_video
        self.num_hands = num_hands

        # Detection parameters
        self.min_detection_confidence = 0.5
        self.min_presence_confidence = 0.5
        self.min_tracking_confidence = 0.5

        # Initialize components
        self.landmarker = None
        self.cap = None
        self.is_running = False

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
            dict: {'Left': [thumb, index, middle, ring, pinky],
                   'Right': [thumb, index, middle, ring, pinky]}

            Each finger is a list of landmarks (x,y,z) tuples:
            - thumb: landmarks 0-4 (wrist shared, then 4 thumb joints)
            - index: landmarks 0, 5-8 (wrist shared, then 4 finger joints)
            - middle: landmarks 0, 9-12
            - ring: landmarks 0, 13-16
            - pinky: landmarks 0, 17-20

            If normalize=True:
            - All coordinates are relative to the wrist (wrist becomes origin 0,0,0)
            - Scaled by hand size (distance from wrist to middle finger MCP)
            - Makes hand pose consistent regardless of distance from camera
        """
        hands_data = {}

        if detection_result.hand_landmarks and detection_result.handedness:
            for i, (hand_landmarks, handedness) in enumerate(
                    zip(detection_result.hand_landmarks, detection_result.handedness)):

                # Get hand label (Left or Right)
                hand_label = handedness[0].category_name

                # Convert all landmarks to list of (x,y,z) tuples
                all_landmarks = []
                for landmark in hand_landmarks:
                    all_landmarks.append((landmark.x, landmark.y, landmark.z))

                if normalize:
                    # Normalize coordinates relative to wrist and hand size
                    wrist = np.array(all_landmarks[0])

                    # Calculate hand size (distance from wrist to middle finger MCP joint)
                    middle_mcp = np.array(all_landmarks[9])
                    hand_size = np.linalg.norm(middle_mcp - wrist)

                    # Avoid division by zero
                    if hand_size < 1e-6:
                        hand_size = 1.0

                    # Normalize all landmarks
                    normalized_landmarks = []
                    for landmark in all_landmarks:
                        landmark_array = np.array(landmark)
                        # Translate so wrist is at origin, then scale by hand size
                        normalized = (landmark_array - wrist) / hand_size
                        normalized_landmarks.append(tuple(normalized))

                    all_landmarks = normalized_landmarks

                # Organize landmarks by finger
                # Each finger includes the wrist (landmark 0) as the base
                fingers = [
                    [all_landmarks[0], all_landmarks[1], all_landmarks[2],
                     all_landmarks[3], all_landmarks[4]],  # Thumb
                    [all_landmarks[0], all_landmarks[5], all_landmarks[6],
                     all_landmarks[7], all_landmarks[8]],  # Index
                    [all_landmarks[0], all_landmarks[9], all_landmarks[10],
                     all_landmarks[11], all_landmarks[12]],  # Middle
                    [all_landmarks[0], all_landmarks[13], all_landmarks[14],
                     all_landmarks[15], all_landmarks[16]],  # Ring
                    [all_landmarks[0], all_landmarks[17], all_landmarks[18],
                     all_landmarks[19], all_landmarks[20]]  # Pinky
                ]

                hands_data[hand_label] = fingers

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

                    # Optional: Add landmark numbers
                    cv2.putText(image, str(i), (point[0] + 10, point[1] - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255), 1)

        # Add instructions text
        cv2.putText(image, "Press 'q' to quit", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Add hand count info
        hand_count = len(detection_result.hand_landmarks) if detection_result.hand_landmarks else 0
        cv2.putText(image, f"Hands detected: {hand_count}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

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
        frame = cv2.flip(frame, 1)

        # Convert BGR to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Create MediaPipe Image
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        # Perform hand landmark detection
        timestamp_ms = int(cv2.getTickCount() / cv2.getTickFrequency() * 1000)
        detection_result = self.landmarker.detect_for_video(mp_image, timestamp_ms)

        # Call strategize method if landmarks are detected
        if detection_result.hand_landmarks:
            action, data = self.strategizer.strategize(self.get_hands_data(detection_result))
            self.action.takeAction(action, data)

        # Draw landmarks on the frame (for display or debugging)
        annotated_frame = self.draw_landmarks(frame, detection_result)

        return annotated_frame, detection_result

    def run(self, camera_index=0, width=640, height=480):
        """
        Start the hand landmark detection

        Args:
            camera_index (int): Camera index (0 for default camera)
            width (int): Camera width resolution
            height (int): Camera height resolution
        """
        try:
            # Initialize camera
            self._initialize_camera(camera_index, width, height)

            self.is_running = True
            print(f"Starting hand landmark detection. Display video: {self.display_video}")
            if self.display_video:
                print("Press 'q' to quit.")
            else:
                print("Press Ctrl+C to quit.")

            frame_count = 0

            while self.is_running:
                # Read frame from webcam
                ret, frame = self.cap.read()
                if not ret:
                    print("Error: Could not read frame from webcam")
                    break

                # Process the frame
                annotated_frame, detection_result = self.process_frame(frame)

                # Display the frame only if display_video is True
                if self.display_video:
                    cv2.imshow('Hand Landmark Detection', annotated_frame)

                    # Check for 'q' key press to quit (only when displaying video)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

                frame_count += 1

                # Optional: Add frame rate limiting or other processing here

        except KeyboardInterrupt:
            print("\nInterrupted by user")
        except Exception as e:
            print(f"Error occurred: {e}")
        finally:
            self.stop()

    def stop(self):
        """Stop the detection and clean up resources"""
        self.is_running = False

        if self.cap:
            self.cap.release()
            print("Camera released")

        if self.display_video:
            cv2.destroyAllWindows()
            print("OpenCV windows closed")

        print("Hand landmark detector stopped")

    def set_display_video(self, display):
        """
        Set whether to display video feed

        Args:
            display (bool): True to show video, False to hide
        """
        self.display_video = display
        if not display:
            cv2.destroyAllWindows()
