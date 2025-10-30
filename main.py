from backend.Action import Action
from backend.HandTracker import HandTracker
from backend.Strategizer import Strategizer


def main():
    """Main method for the application"""

    action = Action("windows")
    strategizer = Strategizer()

    # Create detector instance with video display and smoothing enabled
    detector = HandTracker(
        strategizer=strategizer,
        action=action,
        model_path='.\\backend\\models\\hand_landmarker.task',
        display_video=True,
        num_hands=2,
        enable_smoothing=True,
        window_size=5,  # Adjust: 3-5 light, 5-10 medium, 10+ heavy smoothing
        debug_smoothing=True,
    )

    # Start detection
    detector.run()


if __name__ == "__main__":
    main()