"""macOS camera permission helpers backed by AVFoundation."""

from __future__ import annotations

import platform
from typing import Callable

CAMERA_PERMISSION_AUTHORIZED = "authorized"
CAMERA_PERMISSION_NOT_DETERMINED = "not_determined"
CAMERA_PERMISSION_DENIED = "denied"
CAMERA_PERMISSION_RESTRICTED = "restricted"
CAMERA_PERMISSION_ERROR = "error"

AVCaptureDevice = None
AVAuthorizationStatusAuthorized = None
AVAuthorizationStatusDenied = None
AVAuthorizationStatusNotDetermined = None
AVAuthorizationStatusRestricted = None
AVMediaTypeVideo = None
AVFOUNDATION_IMPORT_ERROR = None

try:
    from AVFoundation import (
        AVCaptureDevice,
        AVAuthorizationStatusAuthorized,
        AVAuthorizationStatusDenied,
        AVAuthorizationStatusNotDetermined,
        AVAuthorizationStatusRestricted,
        AVMediaTypeVideo,
    )
except ImportError as exc:
    AVFOUNDATION_IMPORT_ERROR = str(exc)


_PENDING_CALLBACKS: set[Callable[[bool], None]] = set()


def _is_macos() -> bool:
    return platform.system() == "Darwin"


def _is_available() -> bool:
    return AVCaptureDevice is not None and AVMediaTypeVideo is not None


def get_camera_permission_status() -> str:
    """Return the current macOS camera authorization state."""
    if not _is_macos():
        return CAMERA_PERMISSION_AUTHORIZED
    if not _is_available():
        return CAMERA_PERMISSION_ERROR

    try:
        status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeVideo)
    except Exception:
        return CAMERA_PERMISSION_ERROR

    if status == AVAuthorizationStatusAuthorized:
        return CAMERA_PERMISSION_AUTHORIZED
    if status == AVAuthorizationStatusNotDetermined:
        return CAMERA_PERMISSION_NOT_DETERMINED
    if status == AVAuthorizationStatusDenied:
        return CAMERA_PERMISSION_DENIED
    if status == AVAuthorizationStatusRestricted:
        return CAMERA_PERMISSION_RESTRICTED
    return CAMERA_PERMISSION_ERROR


def request_camera_permission(callback: Callable[[bool], None]) -> bool:
    """Request camera access on macOS and invoke callback with the result."""
    if not callable(callback):
        raise TypeError("callback must be callable")

    if not _is_macos():
        callback(True)
        return True

    if not _is_available():
        callback(False)
        return False

    def _completion(granted):
        try:
            callback(bool(granted))
        finally:
            _PENDING_CALLBACKS.discard(_completion)

    _PENDING_CALLBACKS.add(_completion)
    try:
        AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVMediaTypeVideo, _completion)
        return True
    except Exception:
        _PENDING_CALLBACKS.discard(_completion)
        callback(False)
        return False
