import unittest
from unittest.mock import patch

from backend.Action import Action


class _FakeMouse:
    def __init__(self):
        self.position = (0, 0)
        self.clicks = []
        self.scrolls = []

    def click(self, button, count):
        self.clicks.append((button, count, tuple(self.position)))

    def scroll(self, delta_x, delta_y):
        self.scrolls.append((delta_x, delta_y, tuple(self.position)))

    def press(self, button):
        self.clicks.append(("press", button, tuple(self.position)))

    def release(self, button):
        self.clicks.append(("release", button, tuple(self.position)))


class _FakeKeyboard:
    def __init__(self):
        self.typed = []
        self.pressed = []
        self.released = []

    def press(self, key):
        self.pressed.append(key)

    def release(self, key):
        self.released.append(key)

    def type(self, text):
        self.typed.append(text)


class _FakeQtPoint:
    def __init__(self, x, y):
        self._x = int(x)
        self._y = int(y)

    def x(self):
        return self._x

    def y(self):
        return self._y


class _FakeQtCursor:
    position = (0, 0)

    @classmethod
    def pos(cls):
        return _FakeQtPoint(*cls.position)

    @classmethod
    def setPos(cls, x, y):
        cls.position = (int(x), int(y))


class ActionTutorialScopeTests(unittest.TestCase):
    def test_mouse_moves_are_clamped_to_tutorial_bounds(self):
        with patch.object(Action, "_qt_cursor_api", return_value=None):
            action = Action(mouse=_FakeMouse(), keyboard_test=_FakeKeyboard(), osType="Test")
            action.set_tutorial_scope(bounds=(10, 20, 80, 60))

            action.move_cursor(500, 500)
            action._action_queue.join()

            self.assertEqual(action.mouse.position, (89, 79))
            event = action.get_action_events()[-1]
            self.assertEqual(event["type"], "cursor_move")
            self.assertEqual(event["global_x"], 89)
            self.assertEqual(event["global_y"], 79)
            action.close()

    def test_typing_is_captured_without_sending_os_text(self):
        keyboard = _FakeKeyboard()
        action = Action(mouse=_FakeMouse(), keyboard_test=keyboard, osType="Test")
        action.set_tutorial_scope(capture_text=True)

        action.type_text("hello")
        action._action_queue.join()

        self.assertEqual(keyboard.typed, [])
        event = action.get_action_events()[-1]
        self.assertEqual(event["type"], "type_text")
        self.assertTrue(event["captured"])
        self.assertEqual(event["text"], "hello")
        action.close()

    def test_tap_hotkey_records_shortcut_label_and_cursor_position(self):
        keyboard = _FakeKeyboard()
        with patch.object(Action, "_qt_cursor_api", return_value=None):
            action = Action(mouse=_FakeMouse(), keyboard_test=keyboard, osType="Windows")

            action.move_cursor(120, 240)
            action._action_queue.join()
            action.tap_hotkey(["left_ctrl", "c"])
            action._action_queue.join()

            event = action.get_action_events()[-1]
            self.assertEqual(event["type"], "tap_hotkey")
            self.assertEqual(event["keys"], ["left_ctrl", "c"])
            self.assertEqual(event["shortcut_label"], "Ctrl + C")
            self.assertEqual(event["global_x"], 120)
            self.assertEqual(event["global_y"], 240)
            action.close()

    def test_show_feedback_message_records_label_and_cursor_position(self):
        with patch.object(Action, "_qt_cursor_api", return_value=None):
            action = Action(mouse=_FakeMouse(), keyboard_test=_FakeKeyboard(), osType="Test")

            action.move_cursor(44, 88)
            action._action_queue.join()
            action.show_feedback_message("Keyboard", feedback_type="mode")

            event = action.get_action_events()[-1]
            self.assertEqual(event["type"], "overlay_feedback")
            self.assertEqual(event["label"], "Keyboard")
            self.assertEqual(event["feedback_type"], "mode")
            self.assertEqual(event["global_x"], 44)
            self.assertEqual(event["global_y"], 88)
            action.close()

    def test_tap_hotkey_uses_live_mouse_position_for_overlay_feedback(self):
        mouse = _FakeMouse()
        keyboard = _FakeKeyboard()
        with patch.object(Action, "_qt_cursor_api", return_value=None):
            action = Action(
                mouse=mouse,
                keyboard_test=keyboard,
                osType="Windows",
                screen_origin_x=10,
                screen_origin_y=20,
            )

            mouse.position = (150, 260)
            action.tap_hotkey(["left_ctrl", "c"])
            action._action_queue.join()

            event = action.get_action_events()[-1]
            self.assertEqual(event["type"], "tap_hotkey")
            self.assertEqual(event["global_x"], 150)
            self.assertEqual(event["global_y"], 260)
            self.assertEqual(event["local_x"], 140)
            self.assertEqual(event["local_y"], 240)
            action.close()

    def test_show_feedback_message_uses_live_mouse_position_for_overlay_feedback(self):
        mouse = _FakeMouse()
        with patch.object(Action, "_qt_cursor_api", return_value=None):
            action = Action(
                mouse=mouse,
                keyboard_test=_FakeKeyboard(),
                osType="Test",
                screen_origin_x=25,
                screen_origin_y=40,
            )

            mouse.position = (225, 340)
            action.show_feedback_message("Mouse", feedback_type="mode")

            event = action.get_action_events()[-1]
            self.assertEqual(event["type"], "overlay_feedback")
            self.assertEqual(event["global_x"], 225)
            self.assertEqual(event["global_y"], 340)
            self.assertEqual(event["local_x"], 200)
            self.assertEqual(event["local_y"], 300)
            action.close()

    def test_tap_hotkey_prefers_qt_cursor_coordinates_for_overlay_feedback(self):
        mouse = _FakeMouse()
        keyboard = _FakeKeyboard()
        action = Action(
            mouse=mouse,
            keyboard_test=keyboard,
            osType="Windows",
            screen_origin_x=100,
            screen_origin_y=50,
        )

        mouse.position = (1200, 900)
        _FakeQtCursor.position = (640, 360)
        with patch.object(Action, "_qt_cursor_api", return_value=_FakeQtCursor):
            action.tap_hotkey(["left_ctrl", "c"])
            action._action_queue.join()

        event = action.get_action_events()[-1]
        self.assertEqual(event["type"], "tap_hotkey")
        self.assertEqual(event["global_x"], 640)
        self.assertEqual(event["global_y"], 360)
        self.assertEqual(event["local_x"], 540)
        self.assertEqual(event["local_y"], 310)
        action.close()


if __name__ == "__main__":
    unittest.main()
