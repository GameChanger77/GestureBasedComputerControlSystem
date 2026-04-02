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

    def test_camera_to_screen_reaches_full_screen_bounds(self):
        self.assertEqual(camera_to_screen((0.0, 0.0, 0.0), 1920, 1080), (1919, 0))
        self.assertEqual(camera_to_screen((1.0, 1.0, 0.0), 1920, 1080), (0, 1079))
        self.assertEqual(camera_to_screen((-0.25, -0.1, 0.0), 100, 50), (99, 0))
        self.assertEqual(camera_to_screen((1.25, 1.1, 0.0), 100, 50), (0, 49))


if __name__ == "__main__":
    unittest.main()
