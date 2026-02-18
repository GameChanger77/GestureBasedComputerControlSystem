from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class KeyRect:
    key_id: str
    label: str
    x: float
    y: float
    width: float
    height: float = 1.0


class KeyboardLayoutUS:
    """
    Logical US keyboard layout in layout units.

    Includes only the main ANSI typing block (no function row, nav cluster, or numpad).
    """

    def __init__(self):
        self._keys: List[KeyRect] = []
        self._index: Dict[str, KeyRect] = {}
        self.width: float = 15.9
        self.height: float = 5.2
        self._build_layout()

    def _add_key(self, key_id: str, label: str, x: float, y: float, width: float, height: float = 1.0):
        key = KeyRect(key_id=key_id, label=label, x=x, y=y, width=width, height=height)
        self._keys.append(key)
        self._index[key_id] = key

    def _build_layout(self):
        # Main typing rows only
        y = 0.0
        x = 0.0
        row1 = [
            ("backtick", "`"), ("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"),
            ("5", "5"), ("6", "6"), ("7", "7"), ("8", "8"), ("9", "9"),
            ("0", "0"), ("minus", "-"), ("equals", "=")
        ]
        for key_id, label in row1:
            self._add_key(key_id, label, x, y, 1.0)
            x += 1.05
        self._add_key("backspace", "Back", x, y, 2.1)

        y = 1.05
        x = 0.0
        self._add_key("tab", "Tab", x, y, 1.6)
        x += 1.65
        row2 = [
            ("q", "Q"), ("w", "W"), ("e", "E"), ("r", "R"), ("t", "T"),
            ("y", "Y"), ("u", "U"), ("i", "I"), ("o", "O"), ("p", "P"),
            ("left_bracket", "["), ("right_bracket", "]"), ("backslash", "\\")
        ]
        for key_id, label in row2:
            self._add_key(key_id, label, x, y, 1.0)
            x += 1.05

        y = 2.1
        x = 0.0
        self._add_key("caps_lock", "Caps", x, y, 1.9)
        x += 1.95
        row3 = [
            ("a", "A"), ("s", "S"), ("d", "D"), ("f", "F"), ("g", "G"),
            ("h", "H"), ("j", "J"), ("k", "K"), ("l", "L"),
            ("semicolon", ";"), ("quote", "'")
        ]
        for key_id, label in row3:
            self._add_key(key_id, label, x, y, 1.0)
            x += 1.05
        self._add_key("enter", "Enter", x, y, 2.25)

        y = 3.15
        x = 0.0
        self._add_key("left_shift", "Shift", x, y, 2.4)
        x += 2.45
        row4 = [
            ("z", "Z"), ("x", "X"), ("c", "C"), ("v", "V"), ("b", "B"),
            ("n", "N"), ("m", "M"), ("comma", ","), ("period", "."), ("slash", "/")
        ]
        for key_id, label in row4:
            self._add_key(key_id, label, x, y, 1.0)
            x += 1.05
        self._add_key("right_shift", "Shift", x, y, 2.8)

        y = 4.2
        self._add_key("left_ctrl", "Ctrl", 0.0, y, 1.4)
        self._add_key("left_win", "Win", 1.45, y, 1.2)
        self._add_key("left_alt", "Alt", 2.7, y, 1.2)
        self._add_key("space", "Space", 3.95, y, 7.4)
        self._add_key("right_alt", "Alt", 11.4, y, 1.2)
        self._add_key("right_win", "Win", 12.65, y, 1.2)
        self._add_key("right_ctrl", "Ctrl", 13.9, y, 1.9)

    def iter_keys(self) -> Iterable[KeyRect]:
        return self._keys

    def get_key(self, key_id: str) -> Optional[KeyRect]:
        return self._index.get(key_id)

    def key_at(self, x: float, y: float) -> Optional[KeyRect]:
        for key in self._keys:
            if key.x <= x <= key.x + key.width and key.y <= y <= key.y + key.height:
                return key
        return None

    def nearest_key(self, x: float, y: float, max_distance: float = 0.75) -> Optional[KeyRect]:
        best = None
        best_dist = float("inf")
        for key in self._keys:
            cx = key.x + key.width / 2.0
            cy = key.y + key.height / 2.0
            dx = x - cx
            dy = y - cy
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best = key
        if best is not None and best_dist <= max_distance:
            return best
        return None
