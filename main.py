from backend.Action import Action
from backend.HandTracker import HandTracker
from backend.LandmarkSmoother import LandmarkSmoother
from backend.Strategizer import Strategizer
import os
import pyautogui


def main():
    """Main method for the application"""

    # Dynamically get screen resolution (works on Windows and macOS)
    screen_width, screen_height = pyautogui.size()
    print(f"Detected screen resolution: {screen_width}x{screen_height}")

    action = Action("windows")
    strategizer = Strategizer(
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
