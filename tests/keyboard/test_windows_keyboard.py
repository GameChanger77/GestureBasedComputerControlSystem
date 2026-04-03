"""
Tests for Windows keyboard backend with mocked Windows API calls.

Uses mocking to verify keyboard functionality without actually sending keyboard input.
"""

import pytest
import platform
from unittest.mock import Mock, patch, MagicMock


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only tests")
class TestWindowsKeyboardBackend:

    @pytest.fixture
    def backend(self):
        """Initialize Windows keyboard backend with mocked SendInput."""
        with patch('backend.platforms.WindowsKeyboardBackend.ctypes.windll.user32.SendInput') as mock_send:
            # Mock SendInput to return success (1 = sent)
            mock_send.return_value = 1

            from backend.platforms.WindowsKeyboardBackend import WindowsKeyboardBackend
            backend = WindowsKeyboardBackend()
            # Mock the GetLastError function
            backend._get_last_error = Mock(return_value=0)
            assert backend.initialize(), "Failed to initialize Windows backend"

            # Replace SendInput with our mocked version that returns success
            backend._send_input = mock_send

            yield backend
            backend.shutdown()

    def test_backend_initialization(self, backend):
        """Test that backend initializes correctly."""
        assert backend.is_available()
        assert backend.get_failure_reason() is None

    def test_tap_single_key(self, backend):
        """Test tapping a single key - verifies SendInput called without actual input."""
        # tap_key should return True when mocked SendInput succeeds
        result_a = backend.tap_key("a")
        result_space = backend.tap_key("space")
        result_enter = backend.tap_key("enter")

        assert result_a is True, "tap_key('a') should succeed with mocked SendInput"
        assert result_space is True, "tap_key('space') should succeed"
        assert result_enter is True, "tap_key('enter') should succeed"

        # Verify SendInput was called (key down + key up for each key = 6 calls)
        assert backend._send_input.call_count >= 6, "SendInput should be called for each key press/release"

    def test_key_down_up(self, backend):
        """Test pressing and releasing a key."""
        result_down = backend.key_down("left_shift")
        result_up = backend.key_up("left_shift")

        assert result_down is True, "key_down should succeed"
        assert result_up is True, "key_up should succeed"

        # Verify SendInput was called twice (down and up)
        assert backend._send_input.call_count >= 2

    def test_tap_hotkey(self, backend):
        """Test pressing multiple keys as hotkey."""
        # Test Ctrl+C - mocked so it won't actually trigger anything
        result = backend.tap_hotkey(["left_ctrl", "c"])
        assert result is True, "tap_hotkey should succeed with mocked SendInput"

        # Verify SendInput was called for press and release of each key
        # 2 keys × 2 (down/up) = 4 calls
        assert backend._send_input.call_count >= 4

    def test_type_text(self, backend):
        """Test typing text - verifies SendInput called for Unicode without actual typing."""
        result = backend.type_text("test")
        assert result is True, "type_text should succeed with mocked SendInput"

        # Verify SendInput was called for each character (down + up per char)
        # 4 chars × 2 (down/up) = 8 calls
        assert backend._send_input.call_count >= 8

    def test_modifier_keys(self):
        """Test all modifier key combinations."""
        with patch('backend.platforms.WindowsKeyboardBackend.ctypes.windll.user32.SendInput') as mock_send:
            mock_send.return_value = 1

            from backend.platforms.WindowsKeyboardBackend import WindowsKeyboardBackend
            backend = WindowsKeyboardBackend()
            backend._get_last_error = Mock(return_value=0)
            assert backend.initialize(), "Failed to initialize Windows backend"
            backend._send_input = mock_send

            try:
                modifiers = [
                    "left_shift", "right_shift",
                    "left_ctrl", "right_ctrl",
                    "left_alt", "right_alt",
                    "left_win", "right_win",
                ]
                for mod in modifiers:
                    result = backend.tap_key(mod)
                    assert result is True, f"tap_key({mod}) should succeed"
            finally:
                backend.shutdown()

    def test_function_keys(self):
        """Test function key support."""
        with patch('backend.platforms.WindowsKeyboardBackend.ctypes.windll.user32.SendInput') as mock_send:
            mock_send.return_value = 1

            from backend.platforms.WindowsKeyboardBackend import WindowsKeyboardBackend
            backend = WindowsKeyboardBackend()
            backend._get_last_error = Mock(return_value=0)
            assert backend.initialize(), "Failed to initialize Windows backend"
            backend._send_input = mock_send

            try:
                for i in range(1, 13):
                    key = f"f{i}"
                    result = backend.tap_key(key)
                    assert result is True, f"tap_key({key}) should succeed"
            finally:
                backend.shutdown()

    def test_arrow_keys(self):
        """Test arrow key support."""
        with patch('backend.platforms.WindowsKeyboardBackend.ctypes.windll.user32.SendInput') as mock_send:
            mock_send.return_value = 1

            from backend.platforms.WindowsKeyboardBackend import WindowsKeyboardBackend
            backend = WindowsKeyboardBackend()
            backend._get_last_error = Mock(return_value=0)
            assert backend.initialize(), "Failed to initialize Windows backend"
            backend._send_input = mock_send

            try:
                for key in ["arrow_up", "arrow_down", "arrow_left", "arrow_right"]:
                    result = backend.tap_key(key)
                    assert result is True, f"tap_key({key}) should succeed"
            finally:
                backend.shutdown()

    def test_special_keys(self):
        """Test special key support."""
        with patch('backend.platforms.WindowsKeyboardBackend.ctypes.windll.user32.SendInput') as mock_send:
            mock_send.return_value = 1

            from backend.platforms.WindowsKeyboardBackend import WindowsKeyboardBackend
            backend = WindowsKeyboardBackend()
            backend._get_last_error = Mock(return_value=0)
            assert backend.initialize(), "Failed to initialize Windows backend"
            backend._send_input = mock_send

            try:
                special_keys = [
                    "escape", "tab", "backspace", "enter", "space",
                    "delete", "home", "end", "page_up", "page_down",
                    "insert", "caps_lock"
                ]
                for key in special_keys:
                    result = backend.tap_key(key)
                    assert result is True, f"tap_key({key}) should succeed"
            finally:
                backend.shutdown()

    def test_numpad_keys(self):
        """Test numpad key support."""
        with patch('backend.platforms.WindowsKeyboardBackend.ctypes.windll.user32.SendInput') as mock_send:
            mock_send.return_value = 1

            from backend.platforms.WindowsKeyboardBackend import WindowsKeyboardBackend
            backend = WindowsKeyboardBackend()
            backend._get_last_error = Mock(return_value=0)
            assert backend.initialize(), "Failed to initialize Windows backend"
            backend._send_input = mock_send

            try:
                numpad_keys = [
                    "numpad0", "numpad1", "numpad2", "numpad3", "numpad4",
                    "numpad5", "numpad6", "numpad7", "numpad8", "numpad9",
                    "numpad_add", "numpad_subtract", "numpad_multiply", "numpad_divide"
                ]
                for key in numpad_keys:
                    result = backend.tap_key(key)
                    assert result is True, f"tap_key({key}) should succeed"
            finally:
                backend.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
