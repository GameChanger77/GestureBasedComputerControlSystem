import sys
import os
import pyautogui
from PySide6.QtWidgets import QApplication

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

    # Create HandTracker (now a QThread)
    hand_tracker = HandTracker(
        strategizer=strategizer,
        action=action,
        model_path=os.path.join('.', 'backend', 'models', 'hand_landmarker.task'),
        num_hands=2
    )

    # Create and setup main window
    main_window = MainWindow()
    main_window.set_components(hand_tracker, strategizer, action)
    main_window.show()

    print("Qt Application started. Close window to exit.")

    # Run Qt event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
