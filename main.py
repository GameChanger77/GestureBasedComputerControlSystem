import sys
import os
import pyautogui
from PySide6.QtWidgets import QApplication
from paths import resource
from backend.Action import Action
from backend.HandTracker import HandTracker
from backend.Strategizer import Strategizer
from backend.GestureConfig import GestureConfig
from frontend.main_window import MainWindow

def main():
    """Main application entry point"""
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Hand Gesture Control")
    app.setStyle("Fusion")  # Use Fusion style for consistent look across platforms

    # Dynamically get screen resolution (works on Windows and macOS)
    screen_width, screen_height = pyautogui.size()
    print(f"Detected screen resolution: {screen_width}x{screen_height}")

    # Create backend components
    action = Action()
    # Load gesture configuration (uses defaults if no config file exists)
    config = GestureConfig()
    strategizer = Strategizer(
        action=action,
        config=config,
        screen_width=screen_width,
        screen_height=screen_height
    )
    max_tracked_hands = int(config.get('max_tracked_hands', 1))
    if max_tracked_hands < 1:
        max_tracked_hands = 1

    # Create HandTracker (now a QThread)
    hand_tracker = HandTracker(
        strategizer=strategizer,
        action=action,
        model_path=str(resource(r"backend/models/hand_landmarker.task")),
        num_hands=max_tracked_hands,
        config=config
    )

    # Create and setup main window
    main_window = MainWindow()
    main_window.set_components(hand_tracker, strategizer, action, config=config)
    main_window.show()

    print("Qt Application started. Close window to exit.")

    # Run Qt event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
