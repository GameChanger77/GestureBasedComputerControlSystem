import json
import os


class GestureConfig:
    """
    Configuration manager for gesture recognition parameters.

    Loads settings from gesture_config.json file, with fallback to defaults.
    Allows easy tweaking of thresholds and sensitivities without code changes.
    """

    # Default configuration values
    DEFAULT_CONFIG = {
        # Finger detection
        "finger_extension_angle": 155.0,  # Minimum angle (degrees) for finger to be considered extended

        # Scroll settings
        "scroll_sensitivity": 100,  # Multiplier for scroll speed (higher = faster)

        # Click/Pinch detection
        "pinch_threshold": 0.15,  # Maximum distance for pinch detection (wrist-relative units)

        # Debouncing (gesture confirmation)
        "mouse_tracking_pending_frames": 1,  # Frames to confirm mouse tracking
        "click_pending_frames": 3,  # Frames to confirm click gesture
        "scroll_pending_frames": 2,  # Frames to confirm scroll gesture
        "ending_frames": 2,  # Frames in ending state before reset

        # Mouse move action throttling (reduces system-call churn)
        "mouse_move_min_delta_px": 2,  # Minimum pixel delta before sending cursor update
        "mouse_move_cadence_ms": 75,  # Force update cadence even for tiny motion

        # Screen margins
        "screen_safe_margin": 50,  # Pixels from screen edge to prevent hot corners

        # Performance tuning
        "target_max_fps": 60,  # Cap capture/inference submission loop at this FPS
        "show_landmarks_default": False,  # Draw landmarks in preview by default
        "preview_max_fps": 30,  # Cap UI preview refresh rate (tracking still runs at full speed)
        "camera_buffer_size": 1,  # Camera capture buffer for lower-latency reads
        "pipeline_metrics_window": 120,  # Rolling window size for FPS/latency metrics

        # Hand tracker confidence thresholds (tracking vs re-detection tuning)
        "hand_min_detection_confidence": 0.5,
        "hand_min_presence_confidence": 0.5,
        "hand_min_tracking_confidence": 0.5,

        # Debug mode
        "debug_mode": True  # Enable debug logging
    }

    def __init__(self, config_path="gesture_config.json"):
        """
        Initialize configuration.

        Args:
            config_path: Path to JSON config file (relative to project root)
        """
        self.config_path = config_path
        self.config = self.DEFAULT_CONFIG.copy()

        # Try to load from file
        self.load()

    def load(self):
        """Load configuration from JSON file, merging with defaults."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    user_config = json.load(f)

                # Merge user config with defaults (user values override defaults)
                self.config.update(user_config)
                print(f"Loaded gesture config from {self.config_path}")

            except Exception as e:
                print(f"Error loading config file: {e}")
                print(f"Using default configuration")
        else:
            print(f"Config file not found at {self.config_path}")
            print(f"Using default configuration")
            print(f"Run with defaults or create {self.config_path} to customize")

    def save(self):
        """Save current configuration to JSON file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
            print(f"Saved configuration to {self.config_path}")
        except Exception as e:
            print(f"Error saving config file: {e}")

    def get(self, key, default=None):
        """
        Get a configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return self.config.get(key, default)

    def set(self, key, value):
        """
        Set a configuration value.

        Args:
            key: Configuration key
            value: New value
        """
        self.config[key] = value

    def __getitem__(self, key):
        """Allow dict-style access: config['key']"""
        return self.config[key]

    def __setitem__(self, key, value):
        """Allow dict-style setting: config['key'] = value"""
        self.config[key] = value

    def __repr__(self):
        """String representation of config"""
        return f"GestureConfig({self.config})"

    def print_config(self):
        """Print current configuration in readable format"""
        print("\n" + "="*60)
        print("GESTURE CONFIGURATION")
        print("="*60)
        for key, value in sorted(self.config.items()):
            print(f"  {key:30s} = {value}")
        print("="*60 + "\n")
