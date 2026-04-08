#!/usr/bin/env python3
"""
Validation script for cross-platform keyboard support.

Run this script to verify that keyboard functionality is working correctly
on your platform.

Usage:
    python validate_keyboard.py
"""

import platform
import sys
import time


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_section(text):
    """Print a formatted section."""
    print(f"\n► {text}")
    print("-" * 60)


def check_platform():
    """Check and display current platform."""
    system = platform.system()
    release = platform.release()
    print(f"OS: {system} {release}")
    print(f"Python: {platform.python_version()}")
    return system


def check_dependencies(system):
    """Check required dependencies for the platform."""
    print_section("Checking Dependencies")

    required = {
        "Windows": [
            ("ctypes", "Built-in (no installation needed)"),
            ("pynput", "pip list | grep pynput"),
        ],
        "Linux": [
            ("pynput", "pip list | grep pynput"),
            ("xdotool", "which xdotool"),
            ("ydotool", "which ydotool"),
            ("os", "Built-in (session detection)"),
        ],
        "Darwin": [
            ("PyObjC", "pip list | grep PyObjC"),
            ("pynput", "pip list | grep pynput"),
        ],
    }

    deps = required.get(system, [])
    for dep_name, check_cmd in deps:
        try:
            if dep_name == "ctypes":
                import ctypes
                status = "✓ Available"
            elif dep_name == "pynput":
                import pynput
                status = "✓ Available"
            elif dep_name == "PyObjC":
                import Quartz
                status = "✓ Available"
            elif dep_name == "xdotool":
                import shutil
                status = "✓ Available" if shutil.which("xdotool") else "✗ Not installed"
            elif dep_name == "ydotool":
                import shutil
                status = "✓ Available" if shutil.which("ydotool") else "✗ Not installed"
            elif dep_name == "os":
                import os
                status = "✓ Available"
            else:
                status = "? Unknown"
            print(f"  {dep_name:20} {status:20} ({check_cmd})")
        except ImportError:
            print(f"  {dep_name:20} ✗ Not installed      ({check_cmd})")
        except Exception as e:
            print(f"  {dep_name:20} ? Error: {e}")


def check_backend_creation():
    """Test backend creation."""
    print_section("Testing Backend Creation")

    try:
        from backend.platforms import create_keyboard_backend
        backend = create_keyboard_backend()
        print("✓ Backend created successfully")

        # Check availability
        if backend.is_available():
            print("✓ Backend is available")
        else:
            reason = backend.get_failure_reason()
            print(f"✗ Backend not available: {reason}")
            return None

        return backend
    except Exception as e:
        print(f"✗ Failed to create backend: {e}")
        return None


def check_key_operations(backend):
    """Test basic key operations."""
    print_section("Testing Key Operations")

    if backend is None:
        print("✗ Backend not available, skipping key tests")
        return

    try:
        # Test single key tap
        result = backend.tap_key("a")
        if result:
            print("✓ Successfully tapped key 'a'")
        else:
            print("✗ Failed to tap key 'a'")

        # Test space key
        result = backend.tap_key("space")
        if result:
            print("✓ Successfully tapped key 'space'")
        else:
            print("✗ Failed to tap key 'space'")

        # Test hotkey
        result = backend.tap_hotkey(["left_ctrl", "c"])
        if result:
            print("✓ Successfully tapped hotkey Ctrl+C")
        else:
            print("✗ Failed to tap hotkey Ctrl+C")

        print("\n  Note: Key operations may be delayed due to script execution context")

    except Exception as e:
        print(f"✗ Error during key tests: {e}")


def check_text_input(backend):
    """Test text input."""
    print_section("Testing Text Input")

    if backend is None:
        print("✗ Backend not available, skipping text tests")
        return

    try:
        result = backend.type_text("Test123")
        if result:
            print("✓ Successfully called type_text('Test123')")
        else:
            print("✗ Failed to type text")

        print("\n  Note: Text input may be delayed due to script execution context")

    except Exception as e:
        print(f"✗ Error during text input test: {e}")


def check_linux_session_type():
    """Check Linux session type (X11 vs Wayland)."""
    if platform.system() != "Linux":
        return

    import os
    session_type = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    print_section("Linux Session Type Detection")

    if session_type:
        print(f"✓ Session type: {session_type}")
        if session_type == "x11":
            print("  → Using X11: xdotool backend (recommended)")
        elif session_type == "wayland":
            print("  → Using Wayland: ydotool backend (recommended)")
    else:
        print("⚠ Session type not detected (may default to X11)")
        print("  Set XDG_SESSION_TYPE environment variable for proper detection")


def check_key_code_mappings():
    """Check key code mappings."""
    print_section("Checking Key Code Mappings")

    try:
        from backend.gestures.keyboard_mode.KeyCodes import (
            normalize_key,
            get_xdotool_key,
        )

        # Test normalization
        test_keys = {
            "return": "enter",
            "del": "delete",
            "ctrl": "left_ctrl",
            "shift": "left_shift",
            "cmd": "left_win",
        }

        all_pass = True
        for key, expected in test_keys.items():
            result = normalize_key(key)
            if result == expected:
                print(f"✓ normalize_key('{key}') → '{result}'")
            else:
                print(f"✗ normalize_key('{key}') → '{result}' (expected '{expected}')")
                all_pass = False

        if all_pass:
            print("\n✓ All key normalization tests passed")
        else:
            print("\n⚠ Some key normalization tests failed")

    except Exception as e:
        print(f"✗ Error checking key mappings: {e}")


def check_platform_specific(system):
    """Check platform-specific configuration."""
    print_section(f"Platform-Specific Configuration ({system})")

    if system == "Windows":
        print("✓ Windows detected")
        print("  Using SendInput API for keyboard injection")
        print("  Benefits: No external dependencies, lowest latency")

    elif system == "Linux":
        import os
        session = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
        print(f"✓ Linux detected (session: {session or 'unknown'})")

        if session == "x11":
            print("  Recommended: Install xdotool")
            print("    sudo apt install xdotool")
        elif session == "wayland":
            print("  Recommended: Install ydotool")
            print("    sudo apt install ydotool")
            print("    sudo systemctl start ydotool")
        else:
            print("  Recommended: Install both xdotool and ydotool")
            print("    sudo apt install xdotool ydotool")

    elif system == "Darwin":
        print("✓ macOS detected")
        print("  Recommended: Install PyObjC framework")
        print("    pip install pyobjc-framework-ApplicationServices")
    else:
        print(f"⚠ Unknown platform: {system}")


def run_all_checks():
    """Run all validation checks."""
    print_header("Cross-Platform Keyboard Support - Validation")

    # Step 1: Check platform
    system = check_platform()

    # Step 2: Check dependencies
    check_dependencies(system)

    # Step 3: Platform-specific configuration
    check_platform_specific(system)

    # Step 4: Linux session type
    if system == "Linux":
        check_linux_session_type()

    # Step 5: Key code mappings
    check_key_code_mappings()

    # Step 6: Backend creation
    backend = check_backend_creation()

    # Step 7: Key operations
    if backend:
        check_key_operations(backend)
        check_text_input(backend)

        # Cleanup
        backend.shutdown()

    # Final summary
    print_header("Validation Complete")
    print("\n✓ Keyboard support validation finished!")
    print("\nNext steps:")
    print("  1. Review results above")
    print("  2. Install any missing dependencies for your platform")
    print("  3. Run: pytest tests/keyboard/ -v")


if __name__ == "__main__":
    try:
        run_all_checks()
    except KeyboardInterrupt:
        print("\n\nValidation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Validation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

