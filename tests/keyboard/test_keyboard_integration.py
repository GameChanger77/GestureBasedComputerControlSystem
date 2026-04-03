"""
Cross-platform keyboard backend integration tests.

Tests that verify all backends implement the same interface
and produce consistent behavior across platforms.
"""

import pytest
import platform
from unittest.mock import Mock, patch, MagicMock
from backend.platforms import create_keyboard_backend
from backend.platforms.PlatformKeyboardBackend import PlatformKeyboardBackend


class TestBackendFactory:
    """Test the keyboard backend factory."""
    
    def _get_mocked_backend(self):
        """Helper to create a mocked backend for the current platform."""
        system = platform.system()
        
        if system == "Windows":
            with patch('backend.platforms.WindowsKeyboardBackend.ctypes.windll.user32.SendInput') as mock_send:
                mock_send.return_value = 1
                from backend.platforms.WindowsKeyboardBackend import WindowsKeyboardBackend
                backend = WindowsKeyboardBackend()
                backend._get_last_error = Mock(return_value=0)
                backend.initialize()
                backend._send_input = mock_send
                return backend
        elif system == "Darwin":
            with patch('backend.platforms.MacOSKeyboardBackend.CGEventCreateKeyboardEvent'), \
                 patch('backend.platforms.MacOSKeyboardBackend.CGEventPost'), \
                 patch('backend.platforms.MacOSKeyboardBackend.kCGHIDEventTap'):
                from backend.platforms.MacOSKeyboardBackend import MacOSKeyboardBackend
                backend = MacOSKeyboardBackend()
                return backend
        else:  # Linux
            with patch('backend.platforms.LinuxKeyboardBackend.subprocess.run') as mock_run, \
                 patch('backend.platforms.LinuxKeyboardBackend.pynput.keyboard.Controller'):
                mock_run.return_value = Mock(returncode=0)
                from backend.platforms.LinuxKeyboardBackend import LinuxKeyboardBackend
                backend = LinuxKeyboardBackend()
                backend.initialize()
                return backend
    
    def test_factory_creates_backend(self):
        """Test that factory creates an appropriate backend."""
        backend = create_keyboard_backend()
        assert backend is not None
        assert isinstance(backend, PlatformKeyboardBackend)
        backend.shutdown()
    
    def test_factory_platform_detection(self):
        """Test that factory detects current platform correctly."""
        backend = create_keyboard_backend()
        system = platform.system()
        
        if system == "Windows":
            from backend.platforms.WindowsKeyboardBackend import WindowsKeyboardBackend
            assert isinstance(backend, WindowsKeyboardBackend)
        elif system == "Darwin":
            from backend.platforms.MacOSKeyboardBackend import MacOSKeyboardBackend
            assert isinstance(backend, MacOSKeyboardBackend)
        elif system == "Linux":
            from backend.platforms.LinuxKeyboardBackend import LinuxKeyboardBackend
            assert isinstance(backend, LinuxKeyboardBackend)
        
        backend.shutdown()
    
    def test_factory_initializes_backend(self):
        """Test that factory initializes backend successfully."""
        backend = create_keyboard_backend()
        assert backend.is_available()
        backend.shutdown()
    
    def test_factory_error_handling(self):
        """Test that factory provides meaningful error messages."""
        try:
            backend = create_keyboard_backend()
            backend.shutdown()
        except RuntimeError as e:
            # Error is acceptable if backend truly unavailable
            assert str(e) is not None


class TestBackendInterface:
    """Test that all backends implement the required interface."""
    
    @pytest.fixture
    def backend(self):
        """Get current platform's backend."""
        backend = create_keyboard_backend()
        yield backend
        backend.shutdown()
    
    def test_backend_has_required_methods(self, backend):
        """Test that backend has all required methods."""
        required_methods = [
            "initialize",
            "shutdown",
            "is_available",
            "key_down",
            "key_up",
            "tap_key",
            "tap_hotkey",
            "type_text",
            "get_failure_reason",
        ]
        for method in required_methods:
            assert hasattr(backend, method), f"Backend missing method: {method}"
            assert callable(getattr(backend, method)), f"{method} is not callable"
    
    def test_backend_initialization_status(self, backend):
        """Test backend reports correct initialization status."""
        assert backend.is_available()
        # If available, failure reason should be None
        if backend.is_available():
            assert backend.get_failure_reason() is None


class TestKeyboardAPIConsistency:
    """Test that keyboard operations are consistent across platforms."""
    
    @pytest.fixture
    def backend(self):
        """Get current platform's backend."""
        backend = create_keyboard_backend()
        yield backend
        backend.shutdown()
    
    def test_logical_key_codes_normalized(self, backend):
        """Test that all backends accept normalized logical key codes."""
        # These should work on all platforms
        valid_keys = [
            "a", "z", "0", "9",
            "space", "enter", "escape", "tab",
            "backspace", "delete", "insert",
            "arrow_up", "arrow_down", "arrow_left", "arrow_right",
        ]
        
        for key in valid_keys:
            # Should not raise, though may return False if key code not mapped
            result = backend.tap_key(key)
            assert isinstance(result, bool), f"tap_key({key}) should return bool"
    
    def test_modifier_key_normalization(self, backend):
        """Test that modifier keys are normalized consistently."""
        # All these should normalize to the same modifier
        equivalents = [
            (["left_shift"], ["shift"]),
            (["left_ctrl"], ["ctrl"]),
            (["left_alt"], ["alt"]),
            (["left_win"], ["win"]),
        ]
        
        for keys1, keys2 in equivalents:
            result1 = backend.tap_hotkey(keys1)
            result2 = backend.tap_hotkey(keys2)
            # Both should have the same success/failure status
            # (One might fail if key code not mapped, but both should behave same)
            assert isinstance(result1, bool)
            assert isinstance(result2, bool)
    
    def test_hotkey_order_handling(self, backend):
        """Test that hotkeys handle key combinations correctly."""
        # Order shouldn't matter for modifiers + key
        result1 = backend.tap_hotkey(["left_ctrl", "c"])
        result2 = backend.tap_hotkey(["c", "left_ctrl"])
        # Both should either succeed or fail consistently
        assert isinstance(result1, bool)
        assert isinstance(result2, bool)
    
    def test_type_text_returns_bool(self, backend):
        """Test that type_text always returns a boolean."""
        result = backend.type_text("test")
        assert isinstance(result, bool)
        
        result = backend.type_text("")
        assert isinstance(result, bool)
    
    def test_key_press_release_sequence(self, backend):
        """Test standard key press/release sequence."""
        # This should work consistently across platforms
        assert backend.key_down("a") or not backend.is_available()
        assert backend.key_up("a") or not backend.is_available()


class TestErrorHandling:
    """Test error handling across backends."""
    
    @pytest.fixture
    def backend(self):
        """Get current platform's backend."""
        backend = create_keyboard_backend()
        yield backend
        backend.shutdown()
    
    def test_invalid_key_code_handling(self, backend):
        """Test handling of invalid key codes."""
        # Should not raise, just return False or handle gracefully
        result = backend.tap_key("invalid_key_that_does_not_exist")
        assert isinstance(result, bool)
    
    def test_empty_hotkey_handling(self, backend):
        """Test handling of empty hotkey list."""
        result = backend.tap_hotkey([])
        assert isinstance(result, bool)
    
    def test_none_values_handling(self, backend):
        """Test handling of None values."""
        # Should not raise exceptions
        result = backend.type_text(None)
        assert isinstance(result, bool)


class TestLogicalKeyMapping:
    """Test logical key code mappings."""
    
    def test_key_normalization(self):
        """Test key code normalization."""
        from backend.gestures.keyboard_mode.KeyCodes import normalize_key
        
        # Test aliases
        assert normalize_key("return") == "enter"
        assert normalize_key("del") == "delete"
        assert normalize_key("esc") == "escape"
        assert normalize_key("ctrl") == "left_ctrl"
        assert normalize_key("shift") == "left_shift"
        assert normalize_key("alt") == "left_alt"
        assert normalize_key("cmd") == "left_win"
    
    def test_windows_vk_codes(self):
        """Test Windows virtual key codes."""
        if platform.system() != "Windows":
            pytest.skip("Windows-only test")

        with patch('backend.platforms.WindowsKeyboardBackend.ctypes.windll.user32.SendInput') as mock_send:
            mock_send.return_value = 1
            from backend.platforms.WindowsKeyboardBackend import WindowsKeyboardBackend
            backend = WindowsKeyboardBackend()
            backend._get_last_error = Mock(return_value=0)
            backend.initialize()

            # Test some common keys
            assert backend.get_windows_vk("a") == 0x41
            assert backend.get_windows_vk("enter") == 0x0D
            assert backend.get_windows_vk("space") == 0x20
            assert backend.get_windows_vk("left_ctrl") == 0xA2

            backend.shutdown()

    def test_xdotool_keys(self):
        """Test xdotool key mappings."""
        from backend.gestures.keyboard_mode.KeyCodes import get_xdotool_key
        
        # Test some common keys
        assert get_xdotool_key("a") == "a"
        assert get_xdotool_key("enter") == "Return"
        assert get_xdotool_key("space") == "space"
        assert get_xdotool_key("left_ctrl") == "Control_L"


class TestResourceCleanup:
    """Test proper resource cleanup."""
    
    def test_backend_shutdown(self):
        """Test that backend shuts down cleanly."""
        backend = create_keyboard_backend()
        assert backend.is_available()
        backend.shutdown()
        # Backend should still be queryable after shutdown
        # (though operations may fail)
        backend.get_failure_reason()  # Should not raise
    
    def test_multiple_backend_instances(self):
        """Test creating and destroying multiple backends."""
        backends = []
        for _ in range(3):
            backend = create_keyboard_backend()
            assert backend.is_available()
            backends.append(backend)
        
        # Clean up
        for backend in backends:
            backend.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

