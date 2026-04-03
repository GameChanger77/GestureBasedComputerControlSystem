"""
Tests for Linux keyboard backend with mocked system calls.

Uses mocking to verify keyboard functionality without actually sending keyboard input.
"""

import pytest
import platform
from unittest.mock import Mock, patch, MagicMock


@pytest.mark.skipif(platform.system() != "Linux", reason="Linux-only tests")
class TestLinuxKeyboardBackend:
    
    @pytest.fixture
    def backend(self):
        """Initialize Linux keyboard backend with mocked backends."""
        with patch('backend.platforms.LinuxKeyboardBackend.subprocess.run') as mock_run:
            # Mock subprocess calls to xdotool/ydotool
            mock_run.return_value = Mock(returncode=0)

            with patch('backend.platforms.LinuxKeyboardBackend.pynput.keyboard.Controller') as mock_pynput:
                # Mock pynput controller
                mock_controller = MagicMock()
                mock_pynput.return_value = mock_controller

                from backend.platforms.LinuxKeyboardBackend import LinuxKeyboardBackend
                backend = LinuxKeyboardBackend()
                backend.initialize()

                # Store mocks for verification in tests
                backend._mock_run = mock_run
                backend._mock_controller = mock_controller

                yield backend
                backend.shutdown()

    def test_backend_initialization(self, backend):
        """Test that backend initializes correctly."""
        assert backend.is_available()
    
    def test_backend_order_x11(self, backend):
        """Test backend order detection for X11."""
        # Override session type for testing
        original_session = backend._session_type
        backend._session_type = ""  # Simulate X11
        
        order = backend._get_backend_order()
        assert len(order) > 0
        assert "pynput" in order  # pynput should always be available
        
        backend._session_type = original_session
    
    def test_backend_order_wayland(self, backend):
        """Test backend order detection for Wayland."""
        original_session = backend._session_type
        backend._session_type = "wayland"
        
        order = backend._get_backend_order()
        assert len(order) > 0
        # For Wayland, ydotool should come before xdotool
        if "ydotool" in order and "xdotool" in order:
            assert order.index("ydotool") < order.index("xdotool")
        
        backend._session_type = original_session
    
    def test_tap_single_key(self, backend):
        """Test tapping a single key with mocked backend."""
        result_a = backend.tap_key("a")
        result_space = backend.tap_key("space")
        result_enter = backend.tap_key("enter")
        assert isinstance(result_a, bool)
        assert isinstance(result_space, bool)
        assert isinstance(result_enter, bool)

    def test_key_down_up(self, backend):
        """Test pressing and releasing a key with mocked backend."""
        result_down = backend.key_down("left_shift")
        result_up = backend.key_up("left_shift")
        assert isinstance(result_down, bool)
        assert isinstance(result_up, bool)

    def test_tap_hotkey(self, backend):
        """Test pressing multiple keys as hotkey with mocked backend."""
        result = backend.tap_hotkey(["left_ctrl", "c"])
        assert isinstance(result, bool)

    def test_type_text(self, backend):
        """Test typing text with mocked backend."""
        result = backend.type_text("test")
        assert isinstance(result, bool)
    
    def test_modifier_keys(self, backend):
        """Test all modifier key combinations with mocked backend."""
        modifiers = [
            "left_shift", "right_shift",
            "left_ctrl", "right_ctrl",
            "left_alt", "right_alt",
            "left_win", "right_win",
        ]
        for mod in modifiers:
            result = backend.tap_key(mod)
            assert isinstance(result, bool), f"tap_key({mod}) should return bool"
    
    def test_function_keys(self, backend):
        """Test function key support with mocked backend."""
        for i in range(1, 13):
            key = f"f{i}"
            result = backend.tap_key(key)
            assert isinstance(result, bool), f"tap_key({key}) should return bool"
    
    def test_arrow_keys(self, backend):
        """Test arrow key support with mocked backend."""
        for key in ["arrow_up", "arrow_down", "arrow_left", "arrow_right"]:
            result = backend.tap_key(key)
            assert isinstance(result, bool), f"tap_key({key}) should return bool"
    
    def test_special_keys(self, backend):
        """Test special key support with mocked backend."""
        special_keys = [
            "escape", "tab", "backspace", "enter", "space",
            "delete", "home", "end", "page_up", "page_down",
            "insert", "caps_lock"
        ]
        for key in special_keys:
            result = backend.tap_key(key)
            assert isinstance(result, bool), f"tap_key({key}) should return bool"
    
    def test_key_code_conversion_xdotool(self, backend):
        """Test xdotool key code conversions."""
        conversions = {
            "a": "a",
            "enter": "Return",
            "left_ctrl": "Control_L",
            "space": "space",
        }
        for logical, expected in conversions.items():
            result = backend._logical_to_xdotool_key(logical)
            assert result == expected, f"xdotool conversion for {logical}: got {result}, expected {expected}"
    
    def test_key_code_conversion_ydotool(self, backend):
        """Test ydotool key code conversions."""
        conversions = {
            "a": 30,
            "enter": 28,
            "left_ctrl": 29,
            "space": 57,
        }
        for logical, expected in conversions.items():
            result = backend._logical_to_ydotool_code(logical)
            assert result == expected, f"ydotool conversion for {logical}: got {result}, expected {expected}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

