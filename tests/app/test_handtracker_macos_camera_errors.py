import unittest
from unittest.mock import MagicMock, patch

from backend.HandTracker import HandTracker


class _FakeAction:
    def release_all_keys(self):
        return


class HandTrackerMacOSCameraErrorTests(unittest.TestCase):
    def _make_tracker(self):
        return HandTracker(strategizer=object(), action=_FakeAction(), config=None)

    def test_initialize_camera_reports_permission_denied(self):
        tracker = self._make_tracker()
        cap = MagicMock()
        cap.isOpened.return_value = False

        with patch("backend.HandTracker.platform.system", return_value="Darwin"), patch(
            "backend.HandTracker.get_camera_permission_status",
            return_value="denied",
        ), patch(
            "backend.HandTracker.cv2.VideoCapture",
            return_value=cap,
        ):
            with self.assertRaisesRegex(Exception, "Camera access denied"):
                tracker._initialize_camera(camera_backend=1)

    def test_initialize_camera_reports_busy_camera_when_authorized(self):
        tracker = self._make_tracker()
        cap = MagicMock()
        cap.isOpened.return_value = False

        with patch("backend.HandTracker.platform.system", return_value="Darwin"), patch(
            "backend.HandTracker.get_camera_permission_status",
            return_value="authorized",
        ), patch(
            "backend.HandTracker.cv2.VideoCapture",
            return_value=cap,
        ):
            with self.assertRaisesRegex(Exception, "Webcam unavailable or already in use"):
                tracker._initialize_camera(camera_backend=1)

    def test_initialize_camera_reports_permission_restricted(self):
        tracker = self._make_tracker()
        cap = MagicMock()
        cap.isOpened.return_value = False

        with patch("backend.HandTracker.platform.system", return_value="Darwin"), patch(
            "backend.HandTracker.get_camera_permission_status",
            return_value="restricted",
        ), patch(
            "backend.HandTracker.cv2.VideoCapture",
            return_value=cap,
        ):
            with self.assertRaisesRegex(Exception, "Camera access is restricted"):
                tracker._initialize_camera(camera_backend=1)

    def test_initialize_camera_reports_permission_not_determined(self):
        tracker = self._make_tracker()
        cap = MagicMock()
        cap.isOpened.return_value = False

        with patch("backend.HandTracker.platform.system", return_value="Darwin"), patch(
            "backend.HandTracker.get_camera_permission_status",
            return_value="not_determined",
        ), patch(
            "backend.HandTracker.cv2.VideoCapture",
            return_value=cap,
        ):
            with self.assertRaisesRegex(Exception, "has not been granted yet"):
                tracker._initialize_camera(camera_backend=1)


if __name__ == "__main__":
    unittest.main()
