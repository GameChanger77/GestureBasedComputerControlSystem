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
        num_hands=2
    )

    # Start detection
    detector.run()


if __name__ == "__main__":
    main()