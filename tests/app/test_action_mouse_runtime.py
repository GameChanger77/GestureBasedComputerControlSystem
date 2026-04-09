import unittest
from ctypes import wintypes

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
    def press(self, _key):
        pass

    def release(self, _key):
        pass

    def type(self, _text):
        pass


class ActionMouseRuntimeTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(wintypes, "LPVOID"), "Windows ctypes signature only")
    def test_windows_sendinput_uses_lpvoid_argument_binding(self):
        action = Action(mouse=_FakeMouse(), keyboard_test=_FakeKeyboard(), osType="Windows")
        try:
            self.assertEqual(action._send_input.argtypes[1], wintypes.LPVOID)
        finally:
            action.close()

    def test_left_click_uses_press_release_at_target_position(self):
        mouse = _FakeMouse()
        action = Action(mouse=mouse, keyboard_test=_FakeKeyboard(), osType="Test")
        try:
            action.left_click(42, 84)
            action._action_queue.join()

            self.assertEqual(mouse.position, (42, 84))
            self.assertEqual(len(mouse.clicks), 2)
            self.assertEqual(mouse.clicks[0][0], "press")
            self.assertEqual(mouse.clicks[1][0], "release")
            event = action.get_action_events()[-1]
            self.assertEqual(event["type"], "left_click")
            self.assertEqual(event["global_x"], 42)
            self.assertEqual(event["global_y"], 84)
        finally:
            action.close()

    def test_scroll_uses_last_committed_cursor_position(self):
        action = Action(mouse=_FakeMouse(), keyboard_test=_FakeKeyboard(), osType="Test")
        try:
            action.move_cursor(42, 84)
            action._action_queue.join()
            action.scroll(0, 6)
            action._action_queue.join()

            event = action.get_action_events()[-1]
            self.assertEqual(event["type"], "scroll")
            self.assertEqual(event["global_x"], 42)
            self.assertEqual(event["global_y"], 84)
        finally:
            action.close()

    def test_stale_move_generation_is_ignored_after_invalidation(self):
        mouse = _FakeMouse()
        action = Action(mouse=mouse, keyboard_test=_FakeKeyboard(), osType="Test")
        try:
            generation = action._current_move_generation()
            action._invalidate_pending_move_actions()
            action._move_cursor_if_current(99, 101, generation)
            self.assertEqual(mouse.position, (0, 0))
        finally:
            action.close()


if __name__ == "__main__":
    unittest.main()
