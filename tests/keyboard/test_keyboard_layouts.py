import unittest

from backend.HandsData import HandsData
from backend.gestures.keyboard_mode.AirTypingGesture import AirTypingGesture
from backend.gestures.keyboard_mode.KeyboardLayouts import KeyboardLayoutRegistry


class _FakeAction:
    def tap_key(self, key_code):
        _ = key_code

    def tap_hotkey(self, key_codes):
        _ = key_codes

    def type_text(self, text):
        _ = text

    def release_all_keys(self):
        return


class KeyboardLayoutRegistryTests(unittest.TestCase):
    def test_registry_lists_all_supported_layouts(self):
        options = KeyboardLayoutRegistry.list_options()
        values = {option["value"] for option in options}
        self.assertEqual(values, {"qwerty", "azerty", "qwertz", "dvorak", "colemak"})

    def test_azerty_changes_labels_and_swipe_tokens(self):
        layout = KeyboardLayoutRegistry.get("azerty", "Win")
        rows = layout.to_row_items()
        labels = {slot["id"]: slot["label"] for row in rows for slot in row}
        swipe_tokens = {slot["id"]: slot.get("swipe_token") for row in rows for slot in row}

        self.assertEqual(layout.layout_id, "azerty")
        self.assertEqual(labels["q"], "A")
        self.assertEqual(labels["w"], "Z")
        self.assertEqual(labels["a"], "Q")
        self.assertEqual(swipe_tokens["q"], "a")
        self.assertEqual(swipe_tokens["a"], "q")

    def test_airtyping_overlay_uses_selected_layout_and_theme(self):
        gesture = AirTypingGesture(
            _FakeAction(),
            config={
                "keyboard_layout": "azerty",
                "keyboard_theme": "light",
                "keyboard_flip_x_for_mapping": False,
                "pinch_threshold": 0.15,
            },
            priority=15,
        )

        gesture._update_overlay_only(HandsData({}, {}))
        overlay = gesture.get_overlay_data()
        labels = {str(key["id"]): str(key["label"]) for key in overlay.get("keys", [])}

        self.assertEqual(overlay.get("layout_id"), "azerty")
        self.assertEqual(overlay.get("theme_id"), "light")
        self.assertEqual(labels.get("q"), "A")
        self.assertEqual(labels.get("a"), "Q")
        self.assertEqual(gesture._slot_id_to_swipe_token("q"), "a")


if __name__ == "__main__":
    unittest.main()
