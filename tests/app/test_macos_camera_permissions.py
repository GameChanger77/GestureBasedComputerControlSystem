import unittest
from unittest.mock import MagicMock, patch

from backend import macos_camera_permissions as permissions


class MacOSCameraPermissionTests(unittest.TestCase):
    def test_get_camera_permission_status_maps_authorized(self):
        mock_device = MagicMock()
        mock_device.authorizationStatusForMediaType_.return_value = 3

        with patch.object(permissions.platform, "system", return_value="Darwin"), patch.object(
            permissions, "AVCaptureDevice", mock_device
        ), patch.object(permissions, "AVMediaTypeVideo", "video"), patch.object(
            permissions, "AVAuthorizationStatusAuthorized", 3
        ), patch.object(
            permissions, "AVAuthorizationStatusNotDetermined", 0
        ), patch.object(
            permissions, "AVAuthorizationStatusDenied", 2
        ), patch.object(
            permissions, "AVAuthorizationStatusRestricted", 1
        ):
            self.assertEqual(
                permissions.get_camera_permission_status(),
                permissions.CAMERA_PERMISSION_AUTHORIZED,
            )

    def test_get_camera_permission_status_maps_denied(self):
        mock_device = MagicMock()
        mock_device.authorizationStatusForMediaType_.return_value = 2

        with patch.object(permissions.platform, "system", return_value="Darwin"), patch.object(
            permissions, "AVCaptureDevice", mock_device
        ), patch.object(permissions, "AVMediaTypeVideo", "video"), patch.object(
            permissions, "AVAuthorizationStatusAuthorized", 3
        ), patch.object(
            permissions, "AVAuthorizationStatusNotDetermined", 0
        ), patch.object(
            permissions, "AVAuthorizationStatusDenied", 2
        ), patch.object(
            permissions, "AVAuthorizationStatusRestricted", 1
        ):
            self.assertEqual(
                permissions.get_camera_permission_status(),
                permissions.CAMERA_PERMISSION_DENIED,
            )

    def test_get_camera_permission_status_maps_not_determined(self):
        mock_device = MagicMock()
        mock_device.authorizationStatusForMediaType_.return_value = 0

        with patch.object(permissions.platform, "system", return_value="Darwin"), patch.object(
            permissions, "AVCaptureDevice", mock_device
        ), patch.object(permissions, "AVMediaTypeVideo", "video"), patch.object(
            permissions, "AVAuthorizationStatusAuthorized", 3
        ), patch.object(
            permissions, "AVAuthorizationStatusNotDetermined", 0
        ), patch.object(
            permissions, "AVAuthorizationStatusDenied", 2
        ), patch.object(
            permissions, "AVAuthorizationStatusRestricted", 1
        ):
            self.assertEqual(
                permissions.get_camera_permission_status(),
                permissions.CAMERA_PERMISSION_NOT_DETERMINED,
            )

    def test_get_camera_permission_status_maps_restricted(self):
        mock_device = MagicMock()
        mock_device.authorizationStatusForMediaType_.return_value = 1

        with patch.object(permissions.platform, "system", return_value="Darwin"), patch.object(
            permissions, "AVCaptureDevice", mock_device
        ), patch.object(permissions, "AVMediaTypeVideo", "video"), patch.object(
            permissions, "AVAuthorizationStatusAuthorized", 3
        ), patch.object(
            permissions, "AVAuthorizationStatusNotDetermined", 0
        ), patch.object(
            permissions, "AVAuthorizationStatusDenied", 2
        ), patch.object(
            permissions, "AVAuthorizationStatusRestricted", 1
        ):
            self.assertEqual(
                permissions.get_camera_permission_status(),
                permissions.CAMERA_PERMISSION_RESTRICTED,
            )

    def test_request_camera_permission_invokes_callback(self):
        received = []

        class _Device:
            @staticmethod
            def requestAccessForMediaType_completionHandler_(_media_type, callback):
                callback(True)

        with patch.object(permissions.platform, "system", return_value="Darwin"), patch.object(
            permissions, "AVCaptureDevice", _Device
        ), patch.object(permissions, "AVMediaTypeVideo", "video"):
            requested = permissions.request_camera_permission(received.append)

        self.assertTrue(requested)
        self.assertEqual(received, [True])

    def test_request_camera_permission_falls_back_to_false_when_api_unavailable(self):
        received = []

        with patch.object(permissions.platform, "system", return_value="Darwin"), patch.object(
            permissions, "AVCaptureDevice", None
        ), patch.object(permissions, "AVMediaTypeVideo", None):
            requested = permissions.request_camera_permission(received.append)

        self.assertFalse(requested)
        self.assertEqual(received, [False])


if __name__ == "__main__":
    unittest.main()
