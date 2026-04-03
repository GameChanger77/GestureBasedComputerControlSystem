import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from frontend.widgets.tutorial.tutorial_animation_widget import TutorialAnimationWidget


class TutorialAnimationWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])
        cls._repo_root = Path(__file__).resolve().parents[2]
        cls._assets_dir = cls._repo_root / "frontend" / "assets" / "tutorial"

    def test_type_keyboard_falls_back_to_qwerty_when_config_missing(self):
        widget = TutorialAnimationWidget()
        with patch(
            "frontend.widgets.tutorial.tutorial_animation_widget.GestureConfig.resolve_config_path",
            return_value=Path("C:/definitely/missing/gesture_config.json"),
        ):
            self.assertEqual(widget._resolve_keyboard_layout_id(), "qwerty")

    def test_type_keyboard_uses_current_layout_and_resolves_hello_path(self):
        widget = TutorialAnimationWidget()
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "gesture_config.json"
            config_path.write_text(json.dumps({"keyboard_layout": "azerty"}), encoding="utf-8")
            with patch(
                "frontend.widgets.tutorial.tutorial_animation_widget.GestureConfig.resolve_config_path",
                return_value=config_path,
            ):
                widget._refresh_typing_layout()

        self.assertEqual(widget._keyboard_layout_id, "azerty")
        self.assertEqual(len(widget._resolve_swipe_word_slots("hello")), 5)
        _, rendered_slots = widget._build_compact_keyboard_geometry(24.0, 18.0, 520.0, 260.0)
        self.assertEqual(len(widget._typing_path_points(rendered_slots, "hello")), 5)

    def test_keyboard_scenes_render_without_errors(self):
        widget = TutorialAnimationWidget()
        widget.resize(520, 300)
        for asset_name in ("lock_keyboard.json", "unlock_keyboard.json", "type_keyboard.json"):
            widget.set_asset(self._assets_dir / asset_name)
            pixmap = QPixmap(widget.size())
            widget.render(pixmap)


if __name__ == "__main__":
    unittest.main()
