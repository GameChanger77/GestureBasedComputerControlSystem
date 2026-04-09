"""
Tests for the macOS keyboard backend with mocked Quartz calls.
"""

from unittest.mock import ANY, MagicMock, patch

import pytest

from backend.platforms.MacOSKeyboardBackend import MacOSKeyboardBackend


@pytest.fixture
def backend():
    mock_event = MagicMock()
    with patch("backend.platforms.MacOSKeyboardBackend.CGEventCreateKeyboardEvent", return_value=mock_event), patch(
        "backend.platforms.MacOSKeyboardBackend.CGEventKeyboardSetUnicodeString"
    ) as mock_set_unicode, patch(
        "backend.platforms.MacOSKeyboardBackend.CGEventPost"
    ) as mock_post, patch("backend.platforms.MacOSKeyboardBackend.CGEventSetFlags"), patch(
        "backend.platforms.MacOSKeyboardBackend.kCGHIDEventTap", new=1
    ), patch(
        "backend.platforms.MacOSKeyboardBackend.kCGEventFlagMaskShift", new=1 << 17
    ), patch(
        "backend.platforms.MacOSKeyboardBackend.kCGEventFlagMaskControl", new=1 << 18
    ), patch(
        "backend.platforms.MacOSKeyboardBackend.kCGEventFlagMaskAlternate", new=1 << 19
    ), patch(
        "backend.platforms.MacOSKeyboardBackend.kCGEventFlagMaskCommand", new=1 << 20
    ):
        backend_instance = MacOSKeyboardBackend()
        backend_instance.MODIFIER_FLAG_BY_KEY = {
            "left_shift": 1 << 17,
            "right_shift": 1 << 17,
            "left_ctrl": 1 << 18,
            "right_ctrl": 1 << 18,
            "left_alt": 1 << 19,
            "right_alt": 1 << 19,
            "left_win": 1 << 20,
            "right_win": 1 << 20,
            "left_cmd": 1 << 20,
            "right_cmd": 1 << 20,
        }
        assert backend_instance.initialize()
        backend_instance._test_mock_set_unicode = mock_set_unicode
        backend_instance._test_mock_post = mock_post
        yield backend_instance
        backend_instance.shutdown()


class TestMacOSKeyboardBackend:
    def test_backend_initialization(self, backend):
        assert backend.is_available()
        assert backend.get_failure_reason() is None
        assert backend.KEY_MAPPING["left_cmd"] == 0x37

    def test_tap_single_key(self, backend):
        assert backend.tap_key("a") is True
        assert backend.tap_key("space") is True
        assert backend.tap_key("enter") is True

    def test_key_down_up(self, backend):
        assert backend.key_down("left_shift") is True
        assert backend.key_up("left_shift") is True

    def test_tap_hotkey(self, backend):
        assert backend.tap_hotkey(["left_cmd", "c"]) is True

    def test_type_text_uses_unicode_events(self, backend):
        assert backend.type_text("test") is True
        assert backend._test_mock_set_unicode.call_count == 8
        backend._test_mock_set_unicode.assert_any_call(ANY, 1, "t")
        assert backend._test_mock_post.call_count == 8

    def test_modifier_flags_calculation(self, backend):
        assert backend._modifier_flag_for_key("left_shift") == 1 << 17
        assert backend._modifier_flag_for_key("left_ctrl") == 1 << 18
        assert backend._modifier_flag_for_key("left_alt") == 1 << 19
        assert backend._modifier_flag_for_key("left_cmd") == 1 << 20

    def test_cmd_key_aliases(self, backend):
        assert backend.KEY_MAPPING.get("left_cmd") == backend.KEY_MAPPING.get("left_win")
        assert backend.KEY_MAPPING.get("right_cmd") == backend.KEY_MAPPING.get("right_win")

    def test_release_all_keys(self, backend):
        assert backend.key_down("left_shift") is True
        assert backend.key_down("left_cmd") is True
        backend.release_all_keys()
        assert backend._held_keys == set()
