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

        # Mode switching
        "keyboard_mode_entry_pending_frames": 6,
        "keyboard_mode_exit_pending_frames": 5,
        "keyboard_mode_exit_extension_angle": 150.0,
        "keyboard_mode_exit_max_openness": 0.16,
        "keyboard_mode_exit_max_extension_ratio": 0.90,
        "keyboard_mode_exit_max_avg_finger_angle": 145.0,

        # In-air keyboard typing
        "keyboard_tap_depth_threshold": 0.010,
        "keyboard_tap_velocity_threshold": 0.04,
        "keyboard_release_hysteresis": 0.004,
        "keyboard_min_key_refractory_ms": 70,
        "keyboard_press_hover_frames": 1,
        "keyboard_hover_baseline_alpha": 0.1,
        "keyboard_max_tap_xy_drift": 0.08,
        "keyboard_min_global_key_interval_ms": 0,
        "keyboard_press_bend_threshold_deg": 14.0,
        "keyboard_press_bend_delta_deg": 4.0,
        "keyboard_press_radius_drop": 0.012,
        "keyboard_press_depth_threshold": 0.002,
        "keyboard_press_depth_velocity_threshold": 0.06,
        "keyboard_release_bend_threshold_deg": 10.0,
        "keyboard_release_radius_drop": 0.004,
        "keyboard_release_depth_threshold": 0.004,
        "keyboard_repeat_delay_ms": 450,
        "keyboard_repeat_rate_hz": 8,
        "keyboard_key_sticky_margin": 0.10,
        "keyboard_nearest_key_max_distance": 0.20,
        "keyboard_flip_x_for_mapping": True,
        "keyboard_fixed_center_mode": False,
        "keyboard_fixed_lock_press_plane": True,
        "keyboard_fixed_center_x": 0.5,
        "keyboard_fixed_center_y": 0.58,
        "keyboard_fixed_width": 0.78,
        "keyboard_fixed_height": 0.26,
        "keyboard_wrist_ema_alpha": 0.28,
        "keyboard_hand_half_width_scale": 3.2,
        "keyboard_hand_half_width_min": 0.30,
        "keyboard_hand_half_width_max": 0.42,
        "keyboard_hand_height_ratio": 0.96,
        "keyboard_hand_upward_bias": 0.70,
        "keyboard_hand_vertical_offset": -0.010,
        "keyboard_hand_horizontal_offset_left": 0.0,
        "keyboard_hand_horizontal_offset_right": -0.03,
        "keyboard_hand_vertical_offset_left": -0.03,
        "keyboard_hand_vertical_offset_right": -0.08,
        "keyboard_finger_anchor_row": 0.42,
        "keyboard_finger_anchor_mix_x": 0.60,
        "keyboard_finger_anchor_mix_y": 0.92,
        "keyboard_hand_size_ema_alpha": 0.08,
        "keyboard_y_offset_from_fingertips": -0.01,
        "keyboard_y_offset_from_wrists": -0.06,
        "keyboard_active_fingers": ["index", "middle"],
        "keyboard_assign_hands_by_x": True,
        "keyboard_enforce_side_zones": False,
        "keyboard_side_zone_overlap": 0.16,
        "keyboard_use_thumb_fingers": True,
        "keyboard_require_both_hands": True,
        "keyboard_pause_on_hand_loss": True,
        "keyboard_resume_stability_frames": 4,
        "keyboard_debug_log_interval_sec": 0.8,
        "keyboard_mode_switch_cooldown_sec": 1.0,

        # Screen margins
        "screen_safe_margin": 50,  # Pixels from screen edge to prevent hot corners

        # Camera capture
        "camera_width": 1280,
        "camera_height": 720,

        # Preview
        "preview_flip_horizontal": True,

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
