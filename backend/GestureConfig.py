import json
import os
import sys
from pathlib import Path

from backend.gestures.keyboard_mode.KeyboardLayouts import KeyboardLayoutRegistry
from backend.gestures.keyboard_mode.KeyboardThemes import KeyboardThemeRegistry


class GestureConfig:
    """
    Configuration manager for gesture recognition parameters.

    Loads settings from gesture_config.json file, with fallback to defaults.
    Allows easy tweaking of thresholds and sensitivities without code changes.
    """

    APP_NAME = "gbccs"
    CONFIG_FILENAME = "gesture_config.json"
    FIELD_GROUP_ORDER = [
        "Keyboard",
        "Finger detection",
        "Scroll",
        "Click/pinch",
        "Debouncing",
        "Mouse movement",
        "Performance tuning",
        "Camera runtime tuning",
        "Confidence thresholds",
        "Debug",
    ]
    FIELD_PAGE_ORDER = [
        "Keyboard",
        "Controls",
        "Camera",
        "Performance",
        "Debug",
    ]
    GROUP_TO_PAGE = {
        "Keyboard": "Keyboard",
        "Finger detection": "Controls",
        "Scroll": "Controls",
        "Click/pinch": "Controls",
        "Debouncing": "Controls",
        "Mouse movement": "Controls",
        "Camera runtime tuning": "Camera",
        "Confidence thresholds": "Camera",
        "Performance tuning": "Performance",
        "Debug": "Debug",
    }
    PROD_VISIBLE_KEYS = {
        "keyboard_layout",
        "keyboard_theme",
        "finger_extension_angle",
        "scroll_sensitivity",
        "pinch_threshold",
        "target_max_fps",
        "max_tracked_hands",
        "camera_index",
        "camera_target_fps",
        "camera_auto_exposure",
        "camera_dynamic_exposure",
        "right_hand_only_processing",
    }

    # Default configuration values
    DEFAULT_CONFIG = {
        # Finger detection
        "finger_extension_angle": 155.0,  # Minimum angle (degrees) for finger to be considered extended

        # Scroll settings
        "scroll_sensitivity": 100,  # Multiplier for scroll speed (higher = faster)

        # Click/Pinch detection
        "pinch_threshold": 0.45,  # Maximum distance for pinch detection (wrist-relative units)
        "left_click_hold_time_sec": 1.0,  # Hold duration before emitting a second click

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

        # Keyboard overlay and movement (display-only)
        "keyboard_layout": "qwerty",
        "keyboard_theme": "dark",
        "keyboard_flip_x_for_mapping": True,
        "keyboard_fixed_center_x": 0.5,
        "keyboard_fixed_center_y": 0.58,
        "keyboard_fixed_width": 0.78,
        "keyboard_fixed_height": 0.26,
        "keyboard_wrist_ema_alpha": 0.28,
        "keyboard_hand_half_width_scale": 2.55,
        "keyboard_hand_half_width_min": 0.215,
        "keyboard_hand_half_width_max": 0.335,
        "keyboard_hand_height_ratio": 0.83,
        "keyboard_hand_vertical_offset": -0.010,
        "keyboard_hand_horizontal_offset_left": 0.12,
        "keyboard_hand_horizontal_offset_right": 0.0,
        "keyboard_hand_vertical_offset_left": -0.03,
        "keyboard_hand_vertical_offset_right": -0.08,
        "keyboard_finger_anchor_row": 0.30,
        "keyboard_finger_anchor_mix_x": 0.60,
        "keyboard_finger_anchor_mix_y": 0.92,
        "keyboard_drag_deadzone_margin_x": 0.14,
        "keyboard_drag_deadzone_margin_y": 0.18,
        "keyboard_hand_size_ema_alpha": 0.08,
        "keyboard_mode_switch_cooldown_sec": 1.0,
        "keyboard_swipe_min_points": 4,
        "keyboard_swipe_min_unique_keys": 3,
        "keyboard_swipe_release_pinch_threshold": 0.40,
        "keyboard_swipe_release_pending_frames": 2,
        "keyboard_swipe_tracking_grace_frames": 8,
        "keyboard_flick_selection_window_seconds": 3.0,
        "keyboard_flick_min_displacement": 0.075,
        "keyboard_flick_min_speed": 0.25,
        "keyboard_flick_dominance_ratio": 1.2,

        # Mouse move action throttling (reduces system-call churn)
        "mouse_move_min_delta_px": 1,  # Minimum pixel delta before sending cursor update
        "mouse_move_cadence_ms": 16,  # Force update cadence even for tiny motion

        # Performance tuning
        "target_max_fps": 60,  # Cap capture/inference submission loop at this FPS
        "show_landmarks_default": False,  # Draw landmarks in preview by default
        "preview_max_fps": 30,  # Cap UI preview refresh rate (tracking still runs at full speed)
        "camera_buffer_size": 1,  # Camera capture buffer for lower-latency reads
        "pipeline_metrics_window": 120,  # Rolling window size for FPS/latency metrics
        "max_tracked_hands": 1,  # Only one hand is required so far

        # Camera runtime tuning (best-effort; backend/camera dependent)
        "camera_index": 0,
        "camera_backend": 0,
        "camera_device_path": "",
        "camera_device_name": "",
        "camera_width": 640,
        "camera_height": 480,
        "camera_target_fps": 30,
        "camera_auto_exposure": True,
        "camera_dynamic_exposure": True,  # Manual fallback adaptation when auto exposure is disabled
        "camera_dynamic_exposure_target_luma": 112.0,  # Target average brightness (0-255)
        "camera_dynamic_exposure_tolerance_luma": 14.0,  # Deadband around target to avoid oscillation
        "camera_dynamic_exposure_step": 1.0,  # Exposure property delta per adjustment
        "camera_dynamic_exposure_every_n_frames": 12,  # Run adaptation periodically to keep CPU low
        "camera_dynamic_exposure_min": None,  # Optional clamp for exposure property
        "camera_dynamic_exposure_max": None,  # Optional clamp for exposure property
        "camera_exposure_value": None,  # Manual exposure when auto_exposure is False
        "camera_gain_value": None,  # Manual gain override when supported
        "preview_flip_horizontal": True,
        "camera_warmup_frames": 8,  # Drop first N frames after camera open
        "camera_readback_log": True,
        "capture_latest_frame_only": True,  # Decouple capture/inference and always process newest frame
        "right_hand_only_processing": True,  # Process only right hand for mouse + keyboard modes

        # Hand tracker confidence thresholds (tracking vs re-detection tuning)
        "hand_min_detection_confidence": 0.65,
        "hand_min_presence_confidence": 0.45,
        "hand_min_tracking_confidence": 0.4,

        # Debug mode
        "debug_mode": True  # Enable debug logging
    }

    # UI metadata for generated settings controls.
    FIELD_METADATA = {
        "keyboard_layout": {
            "group": "Keyboard",
            "label": "Keyboard Layout",
            "type": "choice",
            "options": KeyboardLayoutRegistry.list_options(),
        },
        "keyboard_theme": {
            "group": "Keyboard",
            "label": "Keyboard Color Scheme",
            "type": "choice",
            "options": KeyboardThemeRegistry.list_options(),
        },
        "finger_extension_angle": {
            "group": "Finger detection",
            "label": "Finger Extension Angle",
            "type": "float",
            "min": 0.0,
            "max": 180.0,
            "step": 0.5,
            "decimals": 1,
        },
        "scroll_sensitivity": {
            "group": "Scroll",
            "label": "Scroll Sensitivity",
            "type": "int",
            "min": 1,
            "max": 1000,
        },
        "pinch_threshold": {
            "group": "Click/pinch",
            "label": "Pinch Threshold",
            "type": "float",
            "min": 0.01,
            "max": 1.0,
            "step": 0.01,
            "decimals": 3,
        },
        "left_click_hold_time_sec": {
            "group": "Click/pinch",
            "label": "Left Click Hold Time (sec)",
            "type": "float",
            "min": 0.1,
            "max": 3.0,
            "step": 0.05,
            "decimals": 2,
        },
        "mouse_tracking_pending_frames": {
            "group": "Debouncing",
            "label": "Mouse Tracking Pending Frames",
            "type": "int",
            "min": 1,
            "max": 30,
        },
        "click_pending_frames": {
            "group": "Debouncing",
            "label": "Click Pending Frames",
            "type": "int",
            "min": 1,
            "max": 30,
        },
        "scroll_pending_frames": {
            "group": "Debouncing",
            "label": "Scroll Pending Frames",
            "type": "int",
            "min": 1,
            "max": 30,
        },
        "ending_frames": {
            "group": "Debouncing",
            "label": "Ending Frames",
            "type": "int",
            "min": 1,
            "max": 60,
        },
        "mouse_move_min_delta_px": {
            "group": "Mouse movement",
            "label": "Mouse Move Min Delta (px)",
            "type": "int",
            "min": 0,
            "max": 100,
        },
        "mouse_move_cadence_ms": {
            "group": "Mouse movement",
            "label": "Mouse Move Cadence (ms)",
            "type": "int",
            "min": 1,
            "max": 1000,
        },
        "target_max_fps": {
            "group": "Performance tuning",
            "label": "Target Max FPS",
            "type": "int",
            "min": 1,
            "max": 240,
        },
        "show_landmarks_default": {
            "group": "Performance tuning",
            "label": "Show Landmarks By Default",
            "type": "bool",
        },
        "preview_max_fps": {
            "group": "Performance tuning",
            "label": "Preview Max FPS",
            "type": "int",
            "min": 1,
            "max": 240,
        },
        "camera_buffer_size": {
            "group": "Performance tuning",
            "label": "Camera Buffer Size",
            "type": "int",
            "min": 1,
            "max": 16,
        },
        "pipeline_metrics_window": {
            "group": "Performance tuning",
            "label": "Pipeline Metrics Window",
            "type": "int",
            "min": 10,
            "max": 1000,
        },
        "max_tracked_hands": {
            "group": "Performance tuning",
            "label": "Max Tracked Hands",
            "type": "int",
            "min": 1,
            "max": 2,
        },
        "camera_index": {
            "group": "Camera runtime tuning",
            "label": "Camera",
            "type": "choice",
            "options_provider": "camera_options",
        },
        "camera_backend": {
            "group": "Camera runtime tuning",
            "label": "Camera Backend",
            "type": "int",
            "hidden": True,
        },
        "camera_device_path": {
            "group": "Camera runtime tuning",
            "label": "Camera Device Path",
            "type": "string",
            "hidden": True,
        },
        "camera_device_name": {
            "group": "Camera runtime tuning",
            "label": "Camera Device Name",
            "type": "string",
            "hidden": True,
        },
        "camera_target_fps": {
            "group": "Camera runtime tuning",
            "label": "Camera Target FPS",
            "type": "float",
            "min": 1.0,
            "max": 240.0,
            "step": 1.0,
            "decimals": 1,
        },
        "camera_auto_exposure": {
            "group": "Camera runtime tuning",
            "label": "Camera Auto Exposure",
            "type": "bool",
        },
        "camera_dynamic_exposure": {
            "group": "Camera runtime tuning",
            "label": "Camera Dynamic Exposure",
            "type": "bool",
        },
        "camera_dynamic_exposure_target_luma": {
            "group": "Camera runtime tuning",
            "label": "Dynamic Exposure Target Luma",
            "type": "float",
            "min": 0.0,
            "max": 255.0,
            "step": 1.0,
            "decimals": 1,
        },
        "camera_dynamic_exposure_tolerance_luma": {
            "group": "Camera runtime tuning",
            "label": "Dynamic Exposure Tolerance Luma",
            "type": "float",
            "min": 0.0,
            "max": 255.0,
            "step": 0.5,
            "decimals": 1,
        },
        "camera_dynamic_exposure_step": {
            "group": "Camera runtime tuning",
            "label": "Dynamic Exposure Step",
            "type": "float",
            "min": 0.01,
            "max": 100.0,
            "step": 0.1,
            "decimals": 2,
        },
        "camera_dynamic_exposure_every_n_frames": {
            "group": "Camera runtime tuning",
            "label": "Dynamic Exposure Every N Frames",
            "type": "int",
            "min": 1,
            "max": 240,
        },
        "camera_dynamic_exposure_min": {
            "group": "Camera runtime tuning",
            "label": "Dynamic Exposure Min",
            "type": "float",
            "nullable": True,
            "min": -1000.0,
            "max": 1000.0,
            "step": 0.1,
            "decimals": 3,
        },
        "camera_dynamic_exposure_max": {
            "group": "Camera runtime tuning",
            "label": "Dynamic Exposure Max",
            "type": "float",
            "nullable": True,
            "min": -1000.0,
            "max": 1000.0,
            "step": 0.1,
            "decimals": 3,
        },
        "camera_exposure_value": {
            "group": "Camera runtime tuning",
            "label": "Camera Exposure Value",
            "type": "float",
            "nullable": True,
            "min": -1000.0,
            "max": 1000.0,
            "step": 0.1,
            "decimals": 3,
        },
        "camera_gain_value": {
            "group": "Camera runtime tuning",
            "label": "Camera Gain Value",
            "type": "float",
            "nullable": True,
            "min": 0.0,
            "max": 1000.0,
            "step": 0.1,
            "decimals": 3,
        },
        "camera_warmup_frames": {
            "group": "Camera runtime tuning",
            "label": "Camera Warmup Frames",
            "type": "int",
            "min": 0,
            "max": 300,
        },
        "camera_readback_log": {
            "group": "Camera runtime tuning",
            "label": "Camera Readback Log",
            "type": "bool",
        },
        "capture_latest_frame_only": {
            "group": "Performance tuning",
            "label": "Capture Latest Frame Only",
            "type": "bool",
        },
        "right_hand_only_processing": {
            "group": "Performance tuning",
            "label": "Right Hand Only Processing",
            "type": "bool",
        },
        "hand_min_detection_confidence": {
            "group": "Confidence thresholds",
            "label": "Min Detection Confidence",
            "type": "float",
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "decimals": 2,
        },
        "hand_min_presence_confidence": {
            "group": "Confidence thresholds",
            "label": "Min Presence Confidence",
            "type": "float",
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "decimals": 2,
        },
        "hand_min_tracking_confidence": {
            "group": "Confidence thresholds",
            "label": "Min Tracking Confidence",
            "type": "float",
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "decimals": 2,
        },
        "debug_mode": {
            "group": "Debug",
            "label": "Debug Mode",
            "type": "bool",
        },
    }

    def __init__(self, config_path=None):
        """
        Initialize configuration.

        Args:
            config_path: Optional explicit JSON config path.
        """
        self.config_path = self.resolve_config_path(config_path)
        self.config = self.DEFAULT_CONFIG.copy()

        # One-time migration when bundled: copy legacy executable-local config
        # to per-user config path if the new path does not exist yet.
        self._migrate_legacy_bundled_config(config_path_was_default=(config_path is None))

        # Try to load from file
        self.load()

    @classmethod
    def is_bundled(cls):
        """Return True when running as a bundled/frozen application."""
        return bool(getattr(sys, "frozen", False))

    @classmethod
    def resolve_config_path(cls, config_path=None):
        """
        Resolve the effective config path.

        Defaults:
        - Source: repo-root gesture_config.json
        - Bundled: per-user app config directory
        """
        if config_path is not None:
            return Path(config_path).expanduser().resolve()

        if cls.is_bundled():
            return cls._resolve_bundled_user_config_path()

        # Source mode: keep config in repository root.
        return Path(__file__).resolve().parent.parent / cls.CONFIG_FILENAME

    @classmethod
    def _resolve_bundled_user_config_path(cls):
        """Resolve per-user config path for bundled application."""
        if sys.platform.startswith("win"):
            appdata = os.environ.get("APPDATA")
            base_dir = Path(appdata) if appdata else (Path.home() / "AppData" / "Roaming")
        elif sys.platform == "darwin":
            base_dir = Path.home() / "Library" / "Application Support"
        else:
            xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
            base_dir = Path(xdg_config_home) if xdg_config_home else (Path.home() / ".config")

        return base_dir / cls.APP_NAME / cls.CONFIG_FILENAME

    def _migrate_legacy_bundled_config(self, config_path_was_default: bool):
        """One-time import of legacy config from executable directory when bundled."""
        if not config_path_was_default or not self.is_bundled():
            return

        if self.config_path.exists():
            return

        legacy_path = Path(sys.executable).resolve().parent / self.CONFIG_FILENAME
        if not legacy_path.exists() or legacy_path == self.config_path:
            return

        try:
            with legacy_path.open("r", encoding="utf-8") as config_file:
                legacy_config = json.load(config_file)

            if isinstance(legacy_config, dict):
                self.config.update(legacy_config)
                self.save()
                print(
                    f"Migrated legacy config from {legacy_path} to per-user path "
                    f"{self.config_path}"
                )
        except Exception as exc:
            print(f"Warning: Failed to migrate legacy config file: {exc}")

    @classmethod
    def get_field_metadata(cls, key):
        """Return normalized field metadata for settings UI generation."""
        metadata = dict(cls.FIELD_METADATA.get(key, {}))
        default_value = cls.DEFAULT_CONFIG.get(key)

        if "type" not in metadata:
            if isinstance(default_value, bool):
                metadata["type"] = "bool"
            elif isinstance(default_value, int):
                metadata["type"] = "int"
            else:
                metadata["type"] = "float"

        if key.startswith("keyboard_"):
            metadata.setdefault("group", "Keyboard")
        else:
            metadata.setdefault("group", "Debug")
        metadata.setdefault("label", key.replace("_", " ").title())
        metadata.setdefault("nullable", default_value is None)
        return metadata

    @classmethod
    def get_grouped_keys(cls):
        """Return config keys grouped for UI sections in stable order."""
        grouped = {group: [] for group in cls.FIELD_GROUP_ORDER}

        for key in cls.DEFAULT_CONFIG:
            metadata = cls.get_field_metadata(key)
            if metadata.get("hidden"):
                continue
            group_name = metadata["group"]
            grouped.setdefault(group_name, [])
            grouped[group_name].append(key)

        # Drop empty groups so UI does not render empty sections.
        return {group: keys for group, keys in grouped.items() if keys}

    @classmethod
    def is_field_visible(cls, key, ui_mode="dev"):
        """Return True if a config key should be shown in the selected UI mode."""
        if ui_mode == "dev":
            return True
        return key in cls.PROD_VISIBLE_KEYS

    @classmethod
    def get_page_definitions(cls, ui_mode="dev"):
        """Return ordered page -> group -> keys mapping for the settings UI."""
        grouped_keys = cls.get_grouped_keys()
        pages = {page: {} for page in cls.FIELD_PAGE_ORDER}

        for group_name, keys in grouped_keys.items():
            visible_keys = [key for key in keys if cls.is_field_visible(key, ui_mode=ui_mode)]
            if not visible_keys:
                continue

            page_name = cls.GROUP_TO_PAGE.get(group_name, "Debug")
            pages.setdefault(page_name, {})
            pages[page_name][group_name] = visible_keys

        return {page: groups for page, groups in pages.items() if groups}

    def load(self):
        """Load configuration from JSON file, merging with defaults."""
        if self.config_path.exists():
            try:
                with self.config_path.open("r", encoding="utf-8") as config_file:
                    user_config = json.load(config_file)

                if not isinstance(user_config, dict):
                    raise ValueError("Config file must contain a JSON object")

                # Merge user config with defaults (user values override defaults)
                self.config.update(
                    {key: value for key, value in user_config.items() if key in self.DEFAULT_CONFIG}
                )
                self._migrate_legacy_camera_selection()
                print(f"Loaded gesture config from {self.config_path}")

            except Exception as e:
                print(f"Error loading config file: {e}")
                print("Using default configuration")
        else:
            print(f"Config file not found at {self.config_path}")
            print("Using default configuration")
            print(f"Run with defaults or create {self.config_path} to customize")

    def _migrate_legacy_camera_selection(self):
        """Decode older encoded camera indices into explicit backend/index fields."""
        if self.config.get("camera_backend", 0):
            return

        legacy_value = self.config.get("camera_index", 0)
        try:
            legacy_int = int(legacy_value)
        except Exception:
            return

        try:
            from backend.camera_devices import decode_legacy_camera_selection

            decoded_index, decoded_backend = decode_legacy_camera_selection(legacy_int)
        except Exception:
            return

        if decoded_backend and (decoded_index != legacy_int):
            self.config["camera_index"] = decoded_index
            self.config["camera_backend"] = decoded_backend

    def save(self):
        """Save current configuration to JSON file."""
        try:
            self.config = {
                key: self.config.get(key, default_value)
                for key, default_value in self.DEFAULT_CONFIG.items()
            }
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with self.config_path.open("w", encoding="utf-8") as config_file:
                json.dump(self.config, config_file, indent=4)
            print(f"Saved configuration to {self.config_path}")
        except Exception as e:
            print(f"Error saving config file: {e}")
            raise

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
        if key not in self.DEFAULT_CONFIG:
            self.config.pop(key, None)
            return
        self.config[key] = value

    def __getitem__(self, key):
        """Allow dict-style access: config['key']"""
        return self.config[key]

    def __setitem__(self, key, value):
        """Allow dict-style setting: config['key'] = value"""
        if key not in self.DEFAULT_CONFIG:
            self.config.pop(key, None)
            return
        self.config[key] = value

    def __repr__(self):
        """String representation of config"""
        return f"GestureConfig({self.config})"

    def print_config(self):
        """Print current configuration in readable format"""
        print("\n" + "=" * 60)
        print("GESTURE CONFIGURATION")
        print("=" * 60)
        for key, value in sorted(self.config.items()):
            print(f"  {key:30s} = {value}")
        print("=" * 60 + "\n")
