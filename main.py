import argparse
import signal
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QGuiApplication
from PySide6.QtCore import QTimer
from paths import resource
from backend.GestureConfig import GestureConfig


def get_screen_size():
    screen = QGuiApplication.primaryScreen()
    if screen:
        size = screen.size()
        return size.width(), size.height()

    # Fallback: pyautogui (lazy import so it can't kill startup)
    try:
        import pyautogui
        return pyautogui.size()
    except Exception as e:
        print(f"[WARN] Could not get screen size via pyautogui: {e}")
        return 1920, 1080  # safe default


def parse_args(argv):
    """Parse CLI arguments for UI mode selection."""
    parser = argparse.ArgumentParser(description="Hand Gesture Control")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dev", action="store_true", help="Launch development UI")
    mode_group.add_argument("--prod", action="store_true", help="Launch production UI")
    return parser.parse_args(argv[1:])


def resolve_ui_mode(args):
    """Resolve requested/effective UI mode with bundled prod enforcement."""
    requested_mode = None
    if args.dev:
        requested_mode = "dev"
    elif args.prod:
        requested_mode = "prod"

    is_bundled = bool(getattr(sys, "frozen", False))
    if is_bundled:
        if requested_mode == "dev":
            print("[WARN] --dev ignored in bundled build; using prod")
        return "prod"

    return requested_mode or "dev"


def create_backend_components(screen_width, screen_height, config_path, ui_mode):
    """Create backend component graph from current config file."""
    from backend.Action import Action
    from backend.HandTracker import HandTracker
    from backend.Strategizer import Strategizer

    action = Action()
    config = GestureConfig(config_path=config_path)
    strategizer = Strategizer(
        action=action,
        config=config,
        screen_width=screen_width,
        screen_height=screen_height,
        ui_mode=ui_mode,
    )

    max_tracked_hands = int(config.get('max_tracked_hands', 1))
    if max_tracked_hands < 1:
        max_tracked_hands = 1
    if max_tracked_hands > 2:
        max_tracked_hands = 2

    hand_tracker = HandTracker(
        strategizer=strategizer,
        action=action,
        model_path=str(resource(r"backend/models/hand_landmarker.task")),
        num_hands=max_tracked_hands,
        config=config
    )

    return {
        "action": action,
        "config": config,
        "strategizer": strategizer,
        "hand_tracker": hand_tracker,
    }


def main():
    """Main application entry point"""
    args = parse_args(sys.argv)
    effective_ui_mode = resolve_ui_mode(args)

    from frontend.main_window import MainWindow

    # Create Qt application (use sanitized argv after argparse consumed app flags).
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Hand Gesture Control")
    app.setStyle("Fusion")  # Use Fusion style for consistent look across platforms

    # Dynamically get screen resolution (works on Windows and macOS)
    screen_width, screen_height = get_screen_size()
    print(f"Detected screen resolution: {screen_width}x{screen_height}")
    print(f"UI mode: {effective_ui_mode}")

    config_path = GestureConfig.resolve_config_path()
    component_factory = lambda: create_backend_components(
        screen_width=screen_width,
        screen_height=screen_height,
        config_path=config_path,
        ui_mode=effective_ui_mode,
    )
    components = component_factory()

    # Create and setup main window
    main_window = MainWindow(ui_mode=effective_ui_mode, component_factory=component_factory)
    main_window.set_components(
        components["hand_tracker"],
        components["strategizer"],
        components["action"],
        config=components["config"],
    )
    main_window.show()

    def _handle_sigint(signum, frame):
        _ = signum, frame
        print("\n[APP] Ctrl+C received, shutting down.")
        try:
            main_window.close()
        except Exception:
            pass
        app.quit()

    # Ensure Ctrl+C is processed while Qt event loop is running.
    signal.signal(signal.SIGINT, _handle_sigint)
    sigint_timer = QTimer()
    sigint_timer.setInterval(100)
    sigint_timer.timeout.connect(lambda: None)
    sigint_timer.start()

    print("Qt Application started. Close window to exit.")

    # Run Qt event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
