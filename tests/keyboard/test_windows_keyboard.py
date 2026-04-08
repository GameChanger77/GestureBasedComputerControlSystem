"""
Tests for the Windows keyboard backend with mocked SendInput calls.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from backend.platforms.WindowsKeyboardBackend import WindowsKeyboardBackend


@pytest.fixture
def backend():
    mock_send = Mock(return_value=1)
    mock_get_last_error = Mock(return_value=0)
    windll = SimpleNamespace(
        user32=SimpleNamespace(SendInput=mock_send),
        kernel32=SimpleNamespace(GetLastError=mock_get_last_error),
    )

    with patch("backend.platforms.WindowsKeyboardBackend.ctypes.windll", new=windll, create=True):
        backend_instance = WindowsKeyboardBackend()
        assert backend_instance.initialize()
        yield backend_instance
        backend_instance.shutdown()


class TestWindowsKeyboardBackend:
    def test_backend_initialization(self, backend):
        assert backend.is_available()
        assert backend.get_failure_reason() is None
        assert backend.KEY_MAPPING["enter"] == 0x0D

    def test_tap_single_key(self, backend):
        assert backend.tap_key("a") is True
        assert backend.tap_key("space") is True
        assert backend.tap_key("enter") is True
        assert backend._send_input.call_count >= 6

    def test_key_down_up(self, backend):
        assert backend.key_down("left_shift") is True
        assert backend.key_up("left_shift") is True
        assert backend._send_input.call_count >= 2

    def test_tap_hotkey(self, backend):
        assert backend.tap_hotkey(["left_ctrl", "c"]) is True
        assert backend._send_input.call_count >= 4

    def test_type_text(self, backend):
        assert backend.type_text("test") is True
        assert backend._send_input.call_count >= 8

    def test_get_windows_vk(self, backend):
        assert backend.get_windows_vk("a") == 0x41
        assert backend.get_windows_vk("enter") == 0x0D
        assert backend.get_windows_vk("space") == 0x20
        assert backend.get_windows_vk("left_ctrl") == 0xA2

    def test_release_all_keys(self, backend):
        assert backend.key_down("left_shift") is True
        assert backend.key_down("left_ctrl") is True
        backend.release_all_keys()
        assert backend._held_keys == set()
