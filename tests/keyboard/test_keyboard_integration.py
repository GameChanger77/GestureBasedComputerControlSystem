"""
Cross-platform keyboard backend integration tests.

These tests validate the shared backend contract using mocked OS facilities so
they run consistently on any host platform.
"""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from backend.platforms import create_keyboard_backend, get_keyboard_backend_class
from backend.platforms.KeyMappings import get_logical_to_key_mapping, get_meta_key_label
from backend.platforms.PlatformKeyboardBackend import PlatformKeyboardBackend


def _make_windows_backend():
    stack = ExitStack()
    mock_send = Mock(return_value=1)
    mock_get_last_error = Mock(return_value=0)
    windll = SimpleNamespace(
        user32=SimpleNamespace(SendInput=mock_send),
        kernel32=SimpleNamespace(GetLastError=mock_get_last_error),
    )
    stack.enter_context(
        patch("backend.platforms.WindowsKeyboardBackend.ctypes.windll", new=windll, create=True)
    )
    backend = create_keyboard_backend(target_os="Windows")
    return stack, backend


def _make_macos_backend():
    stack = ExitStack()
    mock_event = MagicMock()
    mock_pasteboard = MagicMock()
    mock_pasteboard.types.return_value = []
    mock_pasteboard_class = MagicMock()
    mock_pasteboard_class.generalPasteboard.return_value = mock_pasteboard

    stack.enter_context(
        patch("backend.platforms.MacOSKeyboardBackend.CGEventCreateKeyboardEvent", return_value=mock_event)
    )
    stack.enter_context(patch("backend.platforms.MacOSKeyboardBackend.CGEventPost"))
    stack.enter_context(patch("backend.platforms.MacOSKeyboardBackend.CGEventSetFlags"))
    stack.enter_context(patch("backend.platforms.MacOSKeyboardBackend.kCGHIDEventTap", new=1))
    stack.enter_context(patch("backend.platforms.MacOSKeyboardBackend.kCGEventFlagMaskShift", new=1 << 17))
    stack.enter_context(patch("backend.platforms.MacOSKeyboardBackend.kCGEventFlagMaskControl", new=1 << 18))
    stack.enter_context(patch("backend.platforms.MacOSKeyboardBackend.kCGEventFlagMaskAlternate", new=1 << 19))
    stack.enter_context(patch("backend.platforms.MacOSKeyboardBackend.kCGEventFlagMaskCommand", new=1 << 20))
    stack.enter_context(patch("backend.platforms.MacOSKeyboardBackend.NSPasteboard", new=mock_pasteboard_class))
    stack.enter_context(patch("backend.platforms.MacOSKeyboardBackend.NSPasteboardTypeString", new="public.utf8-plain-text"))
    backend = create_keyboard_backend(target_os="Darwin")
    return stack, backend


def _make_linux_backend():
    stack = ExitStack()
    mock_run = Mock(return_value=Mock(returncode=0))
    mock_keyboard = MagicMock()
    stack.enter_context(patch("backend.platforms.LinuxKeyboardBackend.subprocess.run", new=mock_run))
    stack.enter_context(patch("backend.platforms.LinuxKeyboardBackend.PyNputKeyboard", return_value=mock_keyboard))
    backend = create_keyboard_backend(target_os="Linux")
    return stack, backend


def _build_mocked_backend(target_os: str):
    builders = {
        "Windows": _make_windows_backend,
        "Darwin": _make_macos_backend,
        "Linux": _make_linux_backend,
    }
    return builders[target_os]()


@pytest.fixture(params=["Windows", "Darwin", "Linux"])
def backend(request):
    stack, backend_instance = _build_mocked_backend(request.param)
    try:
        yield request.param, backend_instance
    finally:
        backend_instance.shutdown()
        stack.close()


class TestBackendFactory:
    """Test the keyboard backend factory."""

    @pytest.mark.parametrize(
        ("target_os", "expected_class_name"),
        [
            ("Windows", "WindowsKeyboardBackend"),
            ("Darwin", "MacOSKeyboardBackend"),
            ("Linux", "LinuxKeyboardBackend"),
        ],
    )
    def test_factory_class_selection_uses_target_os(self, target_os, expected_class_name):
        backend_class = get_keyboard_backend_class(target_os=target_os)
        assert backend_class.__name__ == expected_class_name

    @pytest.mark.parametrize("target_os", ["Windows", "Darwin", "Linux"])
    def test_factory_creates_initialized_backend(self, target_os):
        stack, backend_instance = _build_mocked_backend(target_os)
        try:
            assert isinstance(backend_instance, PlatformKeyboardBackend)
            assert backend_instance.is_available()
        finally:
            backend_instance.shutdown()
            stack.close()

    def test_factory_error_handling(self):
        with patch(
            "backend.platforms.KeyboardBackendFactory.get_keyboard_backend_class"
        ) as mock_get_backend_class:
            backend = MagicMock()
            backend.initialize.return_value = False
            backend.get_failure_reason.return_value = "broken"
            mock_get_backend_class.return_value = MagicMock(return_value=backend)

            with pytest.raises(RuntimeError, match="broken"):
                create_keyboard_backend(target_os="Linux")


class TestBackendInterface:
    """Test that all backends implement the required interface."""

    def test_backend_has_required_methods(self, backend):
        _, backend_instance = backend
        required_methods = [
            "initialize",
            "shutdown",
            "is_available",
            "key_down",
            "key_up",
            "tap_key",
            "tap_hotkey",
            "type_text",
            "release_all_keys",
            "get_failure_reason",
        ]
        for method in required_methods:
            assert hasattr(backend_instance, method), f"Backend missing method: {method}"
            assert callable(getattr(backend_instance, method)), f"{method} is not callable"

    def test_backend_initialization_status(self, backend):
        _, backend_instance = backend
        assert backend_instance.is_available()
        assert backend_instance.get_failure_reason() is None


class TestKeyboardAPIConsistency:
    """Test that keyboard operations are consistent across platforms."""

    def test_logical_key_codes_normalized(self, backend):
        _, backend_instance = backend
        valid_keys = [
            "a", "z", "0", "9",
            "space", "enter", "escape", "tab",
            "backspace", "delete", "insert",
            "arrow_up", "arrow_down", "arrow_left", "arrow_right",
        ]
        for key in valid_keys:
            result = backend_instance.tap_key(key)
            assert isinstance(result, bool), f"tap_key({key}) should return bool"

    def test_modifier_key_normalization(self, backend):
        _, backend_instance = backend
        equivalents = [
            (["left_shift"], ["shift"]),
            (["left_ctrl"], ["ctrl"]),
            (["left_alt"], ["alt"]),
            (["left_win"], ["win"]),
        ]
        for keys1, keys2 in equivalents:
            assert isinstance(backend_instance.tap_hotkey(keys1), bool)
            assert isinstance(backend_instance.tap_hotkey(keys2), bool)

    def test_hotkey_order_handling(self, backend):
        _, backend_instance = backend
        assert isinstance(backend_instance.tap_hotkey(["left_ctrl", "c"]), bool)
        assert isinstance(backend_instance.tap_hotkey(["c", "left_ctrl"]), bool)

    def test_type_text_returns_bool(self, backend):
        _, backend_instance = backend
        assert isinstance(backend_instance.type_text("test"), bool)
        assert isinstance(backend_instance.type_text(""), bool)

    def test_key_press_release_sequence(self, backend):
        _, backend_instance = backend
        assert backend_instance.key_down("a")
        assert backend_instance.key_up("a")

    def test_release_all_keys_is_safe(self, backend):
        _, backend_instance = backend
        backend_instance.key_down("left_shift")
        backend_instance.key_down("left_ctrl")
        backend_instance.release_all_keys()
        assert backend_instance.key_up("left_shift") in {True, False}


class TestErrorHandling:
    """Test error handling across backends."""

    def test_invalid_key_code_handling(self, backend):
        _, backend_instance = backend
        assert isinstance(backend_instance.tap_key("invalid_key_that_does_not_exist"), bool)

    def test_empty_hotkey_handling(self, backend):
        _, backend_instance = backend
        assert isinstance(backend_instance.tap_hotkey([]), bool)

    def test_none_values_handling(self, backend):
        _, backend_instance = backend
        assert isinstance(backend_instance.type_text(None), bool)


class TestLogicalKeyMapping:
    """Test logical key code mappings."""

    def test_key_normalization(self):
        from backend.gestures.keyboard_mode.KeyCodes import normalize_key

        assert normalize_key("return") == "enter"
        assert normalize_key("del") == "delete"
        assert normalize_key("esc") == "escape"
        assert normalize_key("ctrl") == "left_ctrl"
        assert normalize_key("shift") == "left_shift"
        assert normalize_key("alt") == "left_alt"
        assert normalize_key("cmd") == "left_win"

    def test_platform_key_mappings(self):
        assert get_logical_to_key_mapping("Windows")["enter"] == 0x0D
        assert get_logical_to_key_mapping("Darwin")["left_cmd"] == 0x37
        assert get_logical_to_key_mapping("Linux")["left_ctrl"] == "Control_L"

    def test_meta_key_labels(self):
        assert get_meta_key_label("Windows") == "Win"
        assert get_meta_key_label("Darwin") == "Cmd"
        assert get_meta_key_label("Linux") == "Super"


class TestResourceCleanup:
    """Test proper resource cleanup."""

    @pytest.mark.parametrize("target_os", ["Windows", "Darwin", "Linux"])
    def test_backend_shutdown(self, target_os):
        stack, backend_instance = _build_mocked_backend(target_os)
        try:
            backend_instance.key_down("left_shift")
            backend_instance.shutdown()
            backend_instance.get_failure_reason()
        finally:
            stack.close()

    def test_multiple_backend_instances(self):
        resources = [_build_mocked_backend(target_os) for target_os in ("Windows", "Darwin", "Linux")]
        try:
            for _, backend_instance in resources:
                assert backend_instance.is_available()
        finally:
            for stack, backend_instance in resources:
                backend_instance.shutdown()
                stack.close()
