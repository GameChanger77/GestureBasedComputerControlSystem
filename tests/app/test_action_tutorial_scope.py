import unittest

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


class ActionTutorialScopeTests(unittest.TestCase):
    def test_mouse_moves_are_clamped_to_tutorial_bounds(self):
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


if __name__ == "__main__":
    unittest.main()
