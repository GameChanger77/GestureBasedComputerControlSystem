from backend.Action import Action
from backend.HandTracker import HandTracker
from backend.LandmarkSmoother import LandmarkSmoother
from backend.Strategizer import Strategizer
import os


def main():
    """Main method for the application"""

    action = Action("windows")
    strategizer = Strategizer()
    smoother = LandmarkSmoother()

    # Create detector instance with video display and smoothing enabled
    detector = HandTracker(
        strategizer=strategizer,
        action=action,
        smoother=smoother,
        model_path=os.path.join('.', 'backend', 'models', 'hand_landmarker.task'),
        display_video=True,
        num_hands=2
    )

    # Start detection
    detector.run()


if __name__ == "__main__":
    main()
