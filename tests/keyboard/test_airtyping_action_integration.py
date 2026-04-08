import unittest

import numpy as np

from backend.Action import Action
from backend.HandsData import HandsData
from backend.gestures.keyboard_mode.AirTypingGesture import AirTypingGesture
from backend.platforms.PlatformKeyboardBackend import PlatformKeyboardBackend


class _FakeMouse:
    def __init__(self):
        self.position = (0, 0)

    def click(self, *_args, **_kwargs):
        return

    def scroll(self, *_args, **_kwargs):
        return

    def press(self, *_args, **_kwargs):
        return

    def release(self, *_args, **_kwargs):
        return


class _FakeKeyboard:
    def press(self, _key):
        return

    def release(self, _key):
        return

    def type(self, _text):
        return


class _RecordingKeyboardBackend(PlatformKeyboardBackend):
    META_KEY_LABEL = "Cmd"

    def __init__(self):
        self._held_keys = set()
        self.tap_key_calls = []
        self.tap_hotkey_calls = []
        self.type_text_calls = []
        self.release_batches = []

    def initialize(self) -> bool:
        return True

    def shutdown(self):
        self.release_all_keys()

    def is_available(self) -> bool:
        return True

    def key_down(self, key_code: str) -> bool:
        self._held_keys.add(str(key_code))
        return True

    def key_up(self, key_code: str) -> bool:
        self._held_keys.discard(str(key_code))
        return True

    def tap_key(self, key_code: str) -> bool:
        self.tap_key_calls.append((str(key_code), set(self._held_keys)))
        return True

    def tap_hotkey(self, key_codes) -> bool:
        self.tap_hotkey_calls.append((list(key_codes), set(self._held_keys)))
        return True

    def type_text(self, text: str) -> bool:
        self.type_text_calls.append((str(text), set(self._held_keys)))
        return True

    def release_all_keys(self):
        self.release_batches.append(set(self._held_keys))
        self._held_keys.clear()

    def get_failure_reason(self):
        return None


def _make_camera_hand(wrist_x: float, index_x: float, index_y: float = 0.42) -> np.ndarray:
    arr = np.zeros((21, 3), dtype=np.float32)
    wrist = np.array([wrist_x, 0.55, 0.0], dtype=np.float32)
    arr[0] = wrist
    arr[4] = wrist + np.array([-0.06, -0.08, 0.0], dtype=np.float32)
    arr[8] = np.array([index_x, index_y, 0.0], dtype=np.float32)
    arr[12] = wrist + np.array([0.04, -0.13, 0.0], dtype=np.float32)
    arr[16] = wrist + np.array([0.06, -0.11, 0.0], dtype=np.float32)
    arr[20] = wrist + np.array([0.08, -0.09, 0.0], dtype=np.float32)
    return arr


def _make_wrist_hand(pinch: bool) -> np.ndarray:
    arr = np.zeros((21, 3), dtype=np.float32)
    arr[0] = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    arr[4] = np.array([0.02, 0.0, 0.0], dtype=np.float32)
    arr[12] = np.array([0.03 if pinch else 0.70, 0.0, 0.0], dtype=np.float32)
    return arr


def _make_hands_data(
    *,
    right_present: bool = True,
    right_pinch: bool = False,
    right_index_x: float = 0.74,
    right_index_y: float = 0.42,
    right_wrist_x: float = 0.78,
) -> HandsData:
    camera = {}
    wrist = {}
    if right_present:
        camera["Right"] = _make_camera_hand(right_wrist_x, right_index_x, right_index_y)
        wrist["Right"] = _make_wrist_hand(right_pinch)
    return HandsData(wrist, camera)


class AirTypingActionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.action = Action(mouse=_FakeMouse(), keyboard_test=_FakeKeyboard(), osType="Darwin")
        self.backend = _RecordingKeyboardBackend()
        self.action._keyboard_backend = self.backend
        self.action._windows_backend = None
        self.action._send_input = None

        self.gesture = AirTypingGesture(
            self.action,
            config={
                "keyboard_swipe_min_points": 3,
                "keyboard_swipe_min_unique_keys": 3,
                "keyboard_swipe_release_pending_frames": 1,
                "keyboard_swipe_tracking_grace_frames": 2,
                "pinch_threshold": 0.15,
                "keyboard_flip_x_for_mapping": False,
            },
            priority=15,
        )
        for _ in range(4):
            self.gesture.update(_make_hands_data(right_present=True, right_pinch=False, right_index_x=0.74))

        self._decode_results = []

        def _decode(_trace, top_k=8):
            _ = top_k
            if self._decode_results:
                return self._decode_results.pop(0)
            return ("hello", 0.92, ["hello", "help", "held", "helm", "hero"])

        self.gesture._swipe_decoder.decode = _decode
        self.gesture._map_tip_to_slot = lambda side, tip, frame: (
            {"id": "h"} if tip[0] < 0.64 else
            {"id": "e"} if tip[0] < 0.68 else
            {"id": "l"} if tip[0] < 0.74 else
            {"id": "o"}
        )

    def tearDown(self):
        self.action.close()

    def _commit_swipe_word(self, word="hello", candidates=None):
        if candidates is None:
            candidates = ["hello", "help", "held", "helm", "hero"]
        self._decode_results.append((word, 0.92, list(candidates)))
        for x in [0.62, 0.66, 0.70, 0.76]:
            self.gesture.update(
                _make_hands_data(
                    right_present=True,
                    right_pinch=True,
                    right_index_x=x,
                    right_index_y=0.60,
                )
            )
        self.gesture.update(
            _make_hands_data(
                right_present=True,
                right_pinch=False,
                right_index_x=0.76,
                right_index_y=0.60,
            )
        )
        self.action._action_queue.join()

    def test_swipe_commit_and_suggestion_replacement_clear_backend_modifiers(self):
        self.backend._held_keys = {"left_cmd"}
        self._commit_swipe_word()

        self.assertEqual(self.backend.release_batches[0], {"left_cmd"})
        self.assertEqual(self.backend.type_text_calls[0], ("hello ", set()))

        overlay = self.gesture.get_overlay_data()
        chip = next(c for c in overlay.get("suggestion_chips", []) if c.get("text") == "help")
        self.backend._held_keys = {"left_cmd"}
        self.gesture.update(
            _make_hands_data(
                right_present=True,
                right_pinch=True,
                right_index_x=chip["x"] + (chip["w"] / 2.0),
                right_index_y=chip["y"] + (chip["h"] / 2.0),
            )
        )
        self.action._action_queue.join()

        self.assertEqual(self.backend.release_batches[:3], [{"left_cmd"}, {"left_cmd"}, set()])
        self.assertEqual(self.backend.type_text_calls[-1], ("help ", set()))
        backspaces = [state for key, state in self.backend.tap_key_calls if key == "backspace"]
        self.assertEqual(len(backspaces), len("hello "))
        self.assertTrue(all(state == set() for state in backspaces))

    def test_delete_last_swipe_word_clears_backend_modifiers_before_backspacing(self):
        self._commit_swipe_word()
        self.backend._held_keys = {"left_cmd"}

        self.assertTrue(self.gesture._delete_last_swipe_word())
        self.action._action_queue.join()

        self.assertEqual(self.backend.release_batches[:2], [set(), {"left_cmd"}])
        backspaces = [state for key, state in self.backend.tap_key_calls if key == "backspace"]
        self.assertEqual(len(backspaces), len("hello "))
        self.assertTrue(all(state == set() for state in backspaces))
        self.assertEqual(self.backend.type_text_calls, [("hello ", set())])


if __name__ == "__main__":
    unittest.main()
