from backend.HandsData import HandsData


class Strategizer:
    def __init__(self, screen_width=1920, screen_height=1080):
        print("Strategizer initialized")
        self.screen_width = screen_width
        self.screen_height = screen_height

        # Thresholds for pinch detection (distance between thumb and index tips)
        self.pinch_threshold = 0.2  # In normalized wrist-relative coordinates
        self.pinch_threshold_squared = 0.04  # Squared threshold (0.2^2) for performance
        self.is_pinching = False

    def strategize(self, hands_data: HandsData):
        """
        Method called when landmarks are detected
        Override this method to implement your custom logic

        Args:
            hands_data: The landmark data for the hands prepared by the get_hands_data method

        Returns:
            Tuple of the action and some information for that data. (action, (data))
        """
        # Use right hand for mouse control
        if hands_data.camera.has_right:
            # Get index finger tip in camera coordinates for mouse position
            index_tip = hands_data.camera.right.index.tip

            if index_tip:
                # Convert camera coordinates to screen coordinates
                mouse_x, mouse_y = self.camera_to_screen(index_tip)

                # Check for pinch gesture (thumb and index finger close together)
                if self.is_pinch_gesture(hands_data.wrist.right):
                    if not self.is_pinching:
                        # Pinch started - perform click
                        self.is_pinching = True
                        return "left_click", (mouse_x, mouse_y)
                else:
                    self.is_pinching = False

                # Move mouse to follow index finger
                return "mouse_move", (mouse_x, mouse_y)

        # Get left hand thumb tip (keeping your dummy code)
        # if hands_data.wrist.has_left:
        #     thumb_tip = hands_data.wrist.left.thumb.tip
        #     print(f"Left thumb tip: {thumb_tip}")

        return None, None

    def camera_to_screen(self, camera_pos):
        """
        Convert camera-relative coordinates to screen coordinates.

        Args:
            camera_pos: Tuple (x, y, z) in camera coordinates (0-1 range)

        Returns:
            Tuple (screen_x, screen_y) in pixel coordinates
        """
        x, y, z = camera_pos

        # Flip x coordinate for mirror effect (camera is mirrored)
        x = 1.0 - x

        # Safe margin to prevent triggering macOS hot corners
        SAFE_MARGIN = 50  # Pixels from screen edges

        # Convert from 0-1 range to screen pixel coordinates
        screen_x = int(x * self.screen_width)
        screen_y = int(y * self.screen_height)

        # Clamp to screen bounds with safe margin to avoid hot corners
        screen_x = max(SAFE_MARGIN, min(self.screen_width - SAFE_MARGIN - 1, screen_x))
        screen_y = max(SAFE_MARGIN, min(self.screen_height - SAFE_MARGIN - 1, screen_y))

        return screen_x, screen_y

    def is_pinch_gesture(self, hand):
        """
        Detect if thumb and index finger are pinched together.

        Args:
            hand: Hand object with wrist-relative coordinates

        Returns:
            bool: True if pinching, False otherwise
        """
        if not hand.exists:
            return False

        thumb_tip = hand.thumb.tip
        index_tip = hand.middle.tip

        if thumb_tip is None or index_tip is None:
            return False

        # Calculate squared distance (avoids expensive sqrt and numpy array creation)
        dx = thumb_tip[0] - index_tip[0]
        dy = thumb_tip[1] - index_tip[1]
        dz = thumb_tip[2] - index_tip[2]
        distance_squared = dx * dx + dy * dy + dz * dz

        # Return True if squared distance is below squared threshold
        return distance_squared < self.pinch_threshold_squared
