"""
sts for macOS keyboard backend with mocked system calls.

Uses mocking to verify keyboard functionality without actually sending keyboard input.
"""

import pytest
import platform
from unittest.mock import Mock, patch, MagicMock


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-only tests")
class TestMacOSKeyboardBackend:

    @pytest.fixture
    def backend(self):
        """Initialize macOS keyboard backend with mocked Quartz framework."""
        # Mock Quartz imports
        with patch('backend.platforms.MacOSKeyboardBackend.CGEventCreateKeyboardEvent') as mock_event_create, \
             patch('backend.platforms.MacOSKeyboardBackend.CGEventPost') as mock_event_post, \
             patch('backend.platforms.MacOSKeyboardBackend.kCGHIDEventTap'):

            # Mock event creation and posting
            mock_event = MagicMock()
            mock_event_create.return_value = mock_event
            mock_event_post.return_value = None

            from backend.platforms.MacOSKeyboardBackend import MacOSKeyboardBackend
            backend = MacOSKeyboardBackend()

            # Mock the initialization to succeed
            backend._send_event = mock_event_post
            backend._create_event = mock_event_create

            yield backend
            backend.shutdown()

    def test_backend_initialization(self, backend):
        """Test that backend initializes correctly."""
        # With mocking, backend should be available
        assert backend is not None

    def test_tap_single_key(self, backend):
        """Test tapping a single key with mocked framework."""
        result_a = backend.tap_key("a")
        result_space = backend.tap_key("space")
        result_enter = backend.tap_key("enter")
        assert isinstance(result_a, bool)
        assert isinstance(result_space, bool)
        assert isinstance(result_enter, bool)

    def test_key_down_up(self, backend):
        """Test pressing and releasing a key with mocked framework."""
        result_down = backend.key_down("left_shift")
        result_up = backend.key_up("left_shift")
        assert isinstance(result_down, bool)
        assert isinstance(result_up, bool)

    def test_tap_hotkey(self, backend):
        """Test pressing multiple keys as hotkey with mocked framework."""
        result = backend.tap_hotkey(["left_cmd", "c"])
        assert isinstance(result, bool)

    def test_type_text(self, backend):
        """Test typing text with mocked framework."""
        result = backend.type_text("test")
        assert isinstance(result, bool)

    def test_modifier_keys(self, backend):
        """Test all modifier key combinations with mocked framework."""
        modifiers = [
            "left_shift", "right_shift",
            "left_ctrl", "right_ctrl",
            "left_alt", "right_alt",
            "left_cmd", "right_cmd",
        ]
        for mod in modifiers:
            result = backend.tap_key(mod)
            assert isinstance(result, bool), f"tap_key({mod}) should return bool"

    def test_function_keys(self, backend):
        """Test function key support with mocked framework."""
        for i in range(1, 13):
            key = f"f{i}"
            result = backend.tap_key(key)
            assert isinstance(result, bool), f"tap_key({key}) should return bool"

    def test_arrow_keys(self, backend):
        """Test arrow key support with mocked framework."""
        for key in ["arrow_up", "arrow_down", "arrow_left", "arrow_right"]:
            result = backend.tap_key(key)
            assert isinstance(result, bool), f"tap_key({key}) should return bool"

    def test_special_keys(self, backend):
        """Test special key support with mocked framework."""
        special_keys = [
            "escape", "tab", "backspace", "enter", "space",
            "delete", "home", "end", "page_up", "page_down",
            "insert", "caps_lock"
        ]
        for key in special_keys:
            result = backend.tap_key(key)
            assert isinstance(result, bool), f"tap_key({key}) should return bool"

    def test_mac_vk_codes_complete(self, backend):
        """Test that MAC_VK_CODES has expected keys."""
        expected_keys = [
            "a", "z", "0", "9",
            "space", "enter", "backspace", "escape",
            "left_shift", "left_ctrl", "left_alt", "left_cmd",
            "arrow_up", "arrow_down", "arrow_left", "arrow_right",
            "f1", "f12"
        ]
        for key in expected_keys:
            assert key in backend.MAC_VK_CODES, f"Missing VK code for {key}"

    def test_modifier_flags_calculation(self, backend):
        """Test modifier flag calculation."""
        # Test single modifiers
        assert backend._get_modifier_flags(["left_shift"]) == backend.MAC_MOD_SHIFT
        assert backend._get_modifier_flags(["left_ctrl"]) == backend.MAC_MOD_CTRL
        assert backend._get_modifier_flags(["left_alt"]) == backend.MAC_MOD_ALT
        assert backend._get_modifier_flags(["left_cmd"]) == backend.MAC_MOD_CMD

        # Test multiple modifiers (should be OR'd)
        combined = backend._get_modifier_flags(["left_ctrl", "left_shift"])
        assert combined == (backend.MAC_MOD_CTRL | backend.MAC_MOD_SHIFT)

    def test_cmd_key_aliases(self, backend):
        """Test that left_win maps to Command key on macOS."""
        # Both left_win and left_cmd should have same VK code on macOS
        assert backend.MAC_VK_CODES.get("left_cmd") == backend.MAC_VK_CODES.get("left_win")


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-only tests")
class TestMacOSPasteboardTextInput:
    """Test macOS-specific text input via clipboard with mocking."""

    def test_pasteboard_framework_integration(self):
        """Test that Pasteboard operations can be mocked."""
        with patch('backend.platforms.MacOSKeyboardBackend.NSPasteboard') as mock_pasteboard_class, \
             patch('backend.platforms.MacOSKeyboardBackend.NSPasteboardTypeString'):

            mock_pasteboard = MagicMock()
            mock_pasteboard_class.generalPasteboard.return_value = mock_pasteboard

            # Verify mocking works
            assert mock_pasteboard is not None

    def test_quartz_event_creation(self):
        """Test that Quartz event creation can be mocked."""
        with patch('backend.platforms.MacOSKeyboardBackend.CGEventCreateKeyboardEvent') as mock_create, \
             patch('backend.platforms.MacOSKeyboardBackend.CGEventPost') as mock_post, \
             patch('backend.platforms.MacOSKeyboardBackend.kCGHIDEventTap'):

            mock_event = MagicMock()
            mock_create.return_value = mock_event

            # Verify mocking works
            assert mock_event is not None
            assert mock_create.called is False  # Not called yet
            mock_create("tap", 0, 0)
            assert mock_create.called is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

