from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import platform

import cv2

try:
    from cv2_enumerate_cameras import enumerate_cameras, supported_backends
except Exception:  # pragma: no cover - fallback for environments missing the dependency
    enumerate_cameras = None
    supported_backends = ()


@dataclass(frozen=True)
class CameraDevice:
    index: int
    backend: int
    name: str
    path: str = ""
    vid: int | None = None
    pid: int | None = None

    @property
    def label(self) -> str:
        return self.name or "Unnamed Camera"


def _preferred_backends():
    """Return backends in a stable, platform-aware preference order."""
    candidates = []
    system = platform.system()

    if system == "Windows":
        candidates.extend([
            getattr(cv2, "CAP_DSHOW", None),
            getattr(cv2, "CAP_MSMF", None),
        ])
    elif system == "Linux":
        candidates.extend([
            getattr(cv2, "CAP_V4L2", None),
            getattr(cv2, "CAP_GSTREAMER", None),
        ])
    elif system == "Darwin":
        candidates.append(getattr(cv2, "CAP_AVFOUNDATION", None))

    preferred = [backend for backend in candidates if backend in supported_backends]
    for backend in supported_backends:
        if backend not in preferred:
            preferred.append(backend)
    return preferred


def _stable_camera_key(camera_info) -> tuple:
    """Build a stable dedupe key for a discovered camera."""
    path = str(getattr(camera_info, "path", "") or "").strip()
    name = str(getattr(camera_info, "name", "") or "").strip()
    vid = getattr(camera_info, "vid", None)
    pid = getattr(camera_info, "pid", None)

    if path:
        normalized_path = path.casefold()
        if normalized_path.startswith("\\\\?\\usb#") and "#{" in normalized_path:
            normalized_path = normalized_path.split("#{", 1)[0]
        return ("path", normalized_path)
    if vid is not None and pid is not None and name:
        return ("usb", int(vid), int(pid), name.casefold())
    if name:
        return ("name", name.casefold())
    return ("backend-index", int(getattr(camera_info, "backend", 0)), int(getattr(camera_info, "index", 0)))


def list_camera_devices() -> list[CameraDevice]:
    """
    Enumerate camera devices using a backend-aware OpenCV enumerator.

    This keeps discovery and capture on the same stack, which avoids the
    name-to-index guessing that caused false positives and noisy probing.
    """
    if enumerate_cameras is None:
        return []

    devices = []
    seen_keys = set()

    for backend in _preferred_backends():
        try:
            discovered = enumerate_cameras(backend)
        except Exception:
            continue

        for camera_info in discovered:
            stable_key = _stable_camera_key(camera_info)
            if stable_key in seen_keys:
                continue

            seen_keys.add(stable_key)
            devices.append(
                CameraDevice(
                    index=int(camera_info.index),
                    backend=int(camera_info.backend),
                    name=str(camera_info.name or "").strip() or "Unnamed Camera",
                    path=str(camera_info.path or "").strip(),
                    vid=int(camera_info.vid) if camera_info.vid is not None else None,
                    pid=int(camera_info.pid) if camera_info.pid is not None else None,
                )
            )

    return devices


def build_camera_options() -> list[dict]:
    """Return dropdown-ready camera options with stable metadata."""
    devices = list_camera_devices()
    if not devices:
        return [
            {
                "label": "Default Camera",
                "index": 0,
                "backend": 0,
                "path": "",
                "name": "Default Camera",
            }
        ]

    name_counts = Counter(device.label for device in devices)
    duplicate_number = Counter()
    options = []

    for device in devices:
        label = device.label
        if name_counts[label] > 1:
            duplicate_number[label] += 1
            label = f"{label} ({duplicate_number[label]})"

        options.append(
            {
                "label": label,
                "index": device.index,
                "backend": device.backend,
                "path": device.path,
                "name": device.label,
            }
        )

    return options


def _normalize_text(value) -> str:
    return str(value or "").strip().casefold()


def resolve_camera_selection(camera_index=0, camera_backend=0, camera_path="", camera_name="") -> CameraDevice:
    """
    Resolve a saved camera selection to the currently available device list.

    Order:
    1. Exact device path match
    2. Unique name match
    3. Exact backend/index match
    4. First available camera
    """
    devices = list_camera_devices()
    if not devices:
        return CameraDevice(
            index=int(camera_index or 0),
            backend=int(camera_backend or 0),
            name=str(camera_name or "Default Camera"),
            path=str(camera_path or ""),
        )

    normalized_path = _normalize_text(camera_path)
    if normalized_path:
        for device in devices:
            if _normalize_text(device.path) == normalized_path:
                return device

    normalized_name = _normalize_text(camera_name)
    if normalized_name:
        matching_names = [device for device in devices if _normalize_text(device.name) == normalized_name]
        if len(matching_names) == 1:
            return matching_names[0]

    saved_backend = int(camera_backend or 0)
    saved_index = int(camera_index or 0)
    for device in devices:
        if device.backend == saved_backend and device.index == saved_index:
            return device

    for device in devices:
        if device.index == saved_index:
            return device

    return devices[0]


def decode_legacy_camera_selection(camera_index):
    """
    Decode a legacy CAP_ANY-encoded OpenCV camera handle into index/backend.

    Older builds stored values like 701 (CAP_DSHOW + device 1). This converts
    those back into explicit backend/index fields.
    """
    try:
        value = int(camera_index)
    except Exception:
        return 0, 0

    for backend in sorted((int(item) for item in supported_backends), reverse=True):
        if value >= backend:
            decoded_index = value - backend
            if decoded_index >= 0:
                return decoded_index, backend

    return value, 0
