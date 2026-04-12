import json
import tempfile
import unittest
from pathlib import Path

from backend.GestureConfig import GestureConfig
from backend.gestures.GestureUtils import camera_to_screen


class GestureConfigCleanupTests(unittest.TestCase):
    def test_legacy_screen_safe_margin_is_dropped_on_load_and_save(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "gesture_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "pinch_threshold": 0.6,
                        "screen_safe_margin": 50,
                    }
                ),
                encoding="utf-8",
            )

            config = GestureConfig(config_path=config_path)

            self.assertEqual(config.get("pinch_threshold"), 0.6)
            self.assertNotIn("screen_safe_margin", config.config)

            config.save()
            saved_payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_payload["pinch_threshold"], 0.6)
            self.assertNotIn("screen_safe_margin", saved_payload)

    def test_legacy_hand_processing_settings_are_dropped_and_dominant_hand_persists(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "gesture_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "dominant_hand": "left",
                        "max_tracked_hands": 2,
                        "right_hand_only_processing": False,
                    }
                ),
                encoding="utf-8",
            )

            config = GestureConfig(config_path=config_path)

            self.assertEqual(config.get("dominant_hand"), "left")
            self.assertNotIn("max_tracked_hands", config.config)
            self.assertNotIn("right_hand_only_processing", config.config)

            config.save()
            saved_payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_payload["dominant_hand"], "left")
            self.assertNotIn("max_tracked_hands", saved_payload)
            self.assertNotIn("right_hand_only_processing", saved_payload)

    def test_screen_interaction_sensitivity_is_clamped_to_new_max(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "gesture_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "screen_interaction_sensitivity": 3.0,
                        "cursor_move_smoothing": 1.0,
                    }
                ),
                encoding="utf-8",
            )

            config = GestureConfig(config_path=config_path)

            self.assertEqual(config.get("screen_interaction_sensitivity"), 2.0)
            self.assertEqual(config.get("cursor_move_smoothing"), 0.85)

    def test_camera_to_screen_reaches_full_screen_bounds(self):
        self.assertEqual(camera_to_screen((0.0, 0.0, 0.0), 1920, 1080), (1919, 0))
        self.assertEqual(camera_to_screen((1.0, 1.0, 0.0), 1920, 1080), (0, 1079))
        self.assertEqual(camera_to_screen((-0.25, -0.1, 0.0), 100, 50), (99, 0))
        self.assertEqual(camera_to_screen((1.25, 1.1, 0.0), 100, 50), (0, 49))

    def test_camera_to_screen_applies_configurable_deadzones(self):
        self.assertEqual(
            camera_to_screen(
                (0.95, 0.95, 0.0),
                100,
                100,
                side_deadzone=0.10,
                top_deadzone=0.0,
                bottom_deadzone=0.20,
            ),
            (0, 99),
        )
        self.assertEqual(
            camera_to_screen(
                (0.50, 0.50, 0.0),
                100,
                100,
                side_deadzone=0.10,
                top_deadzone=0.0,
                bottom_deadzone=0.20,
            ),
            (50, 62),
        )

    def test_camera_to_screen_sensitivity_defaults_to_current_mapping(self):
        self.assertEqual(
            camera_to_screen(
                (0.60, 0.60, 0.0),
                100,
                100,
                flip_x=False,
                sensitivity=1.0,
            ),
            (60, 60),
        )
        self.assertEqual(
            camera_to_screen(
                (0.60, 0.60, 0.0),
                100,
                100,
                flip_x=False,
                sensitivity=2.0,
            ),
            (70, 70),
        )

    def test_camera_to_screen_applies_sensitivity_after_deadzones(self):
        self.assertEqual(
            camera_to_screen(
                (0.50, 0.50, 0.0),
                100,
                100,
                side_deadzone=0.10,
                top_deadzone=0.0,
                bottom_deadzone=0.20,
                flip_x=False,
                sensitivity=2.0,
            ),
            (50, 75),
        )


if __name__ == "__main__":
    unittest.main()
