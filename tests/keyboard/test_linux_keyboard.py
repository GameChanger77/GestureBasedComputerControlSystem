"""
Tests for the Linux keyboard backend with mocked subprocess and pynput calls.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from backend.platforms.LinuxKeyboardBackend import LinuxKeyboardBackend


@pytest.fixture
def backend():
    with patch("backend.platforms.LinuxKeyboardBackend.subprocess.run") as mock_run, patch(
        "backend.platforms.LinuxKeyboardBackend.PyNputKeyboard"
    ) as mock_pynput_keyboard:
        mock_run.return_value = Mock(returncode=0)
        mock_controller = MagicMock()
        mock_pynput_keyboard.return_value = mock_controller

        backend_instance = LinuxKeyboardBackend()
        assert backend_instance.initialize()
        yield backend_instance
        backend_instance.shutdown()


class TestLinuxKeyboardBackend:
    def test_backend_initialization(self, backend):
        assert backend.is_available()
        assert backend.KEY_MAPPING["left_ctrl"] == "Control_L"

    def test_backend_order_x11(self, backend):
        backend._session_type = ""
        order = backend._get_backend_order()
        assert "pynput" in order

    def test_backend_order_wayland(self, backend):
        backend._session_type = "wayland"
        order = backend._get_backend_order()
        assert "pynput" in order
        if "ydotool" in order and "xdotool" in order:
            assert order.index("ydotool") < order.index("xdotool")

    def test_tap_single_key(self, backend):
        assert backend.tap_key("a") is True
        assert backend.tap_key("space") is True
        assert backend.tap_key("enter") is True

    def test_key_down_up(self, backend):
        assert backend.key_down("left_shift") is True
        assert backend.key_up("left_shift") is True

    def test_tap_hotkey(self, backend):
        assert backend.tap_hotkey(["left_ctrl", "c"]) is True

    def test_type_text(self, backend):
        assert backend.type_text("test") is True

    def test_key_code_conversion_xdotool(self, backend):
        assert backend._logical_to_xdotool_key("a") == "a"
        assert backend._logical_to_xdotool_key("enter") == "Return"
        assert backend._logical_to_xdotool_key("left_ctrl") == "Control_L"
        assert backend._logical_to_xdotool_key("space") == "space"

    def test_key_code_conversion_ydotool(self, backend):
        assert backend._logical_to_ydotool_code("a") == 30
        assert backend._logical_to_ydotool_code("enter") == 28
        assert backend._logical_to_ydotool_code("left_ctrl") == 29
        assert backend._logical_to_ydotool_code("space") == 57

    def test_release_all_keys(self, backend):
        backend.key_down("left_shift")
        backend.key_down("left_ctrl")
        backend.release_all_keys()
        assert backend._held_keys == set()
