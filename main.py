from backend.Action import Action
from backend.HandTracker import HandTracker
from backend.Strategizer import Strategizer
from backend.GestureConfig import GestureConfig
import os
import pyautogui


def main():
    """Main method for the application"""

    # Load gesture configuration
    config = GestureConfig("gesture_config.json")
    config.print_config()

    # Dynamically get screen resolution (works on Windows and macOS)
    screen_width, screen_height = pyautogui.size()
    print(f"Detected screen resolution: {screen_width}x{screen_height}")

    action = Action("windows")
    strategizer = Strategizer(
        action=action,
        config=config,
        screen_width=screen_width,
        screen_height=screen_height
    )

    # Create detector instance with video display and smoothing enabled
    detector = HandTracker(
        strategizer=strategizer,
        action=action,
        model_path=os.path.join('.', 'backend', 'models', 'hand_landmarker.task'),
        display_video=True,
        num_hands=2
    )

    # Start detection
    detector.run()


if __name__ == "__main__":
    main()
