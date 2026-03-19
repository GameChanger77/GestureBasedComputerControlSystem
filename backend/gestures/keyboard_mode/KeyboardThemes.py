from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


Color = Tuple[int, int, int, int]


@dataclass(frozen=True)
class KeyboardThemePalette:
    theme_id: str
    label: str
    keyboard_body_fill: Color
    keyboard_body_edge: Color
    key_fill: Color
    key_edge: Color
    key_hover_fill: Color
    key_hover_edge: Color
    key_pressed_fill: Color
    key_pressed_edge: Color
    key_label: Color
    key_label_shadow: Color
    suggestion_fill: Color
    suggestion_edge: Color
    suggestion_hover_fill: Color
    suggestion_hover_edge: Color
    suggestion_label: Color
    suggestion_label_shadow: Color
    swipe_path: Color
    hover_point_fill: Color
    hover_point_edge: Color
    debug_bounds: Color
    debug_panel_fill: Color
    debug_panel_edge: Color
    debug_panel_text: Color
    badge_shadow: Color
    badge_fill: Color
    badge_edge: Color
    lock_shackle_locked: Color
    lock_body_locked: Color
    lock_shackle_unlocked: Color
    lock_body_unlocked: Color


class KeyboardThemeRegistry:
    _THEMES: Dict[str, KeyboardThemePalette] = {
        "dark": KeyboardThemePalette(
            theme_id="dark",
            label="Dark",
            keyboard_body_fill=(24, 28, 34, 220),
            keyboard_body_edge=(150, 160, 175, 190),
            key_fill=(57, 63, 76, 210),
            key_edge=(190, 198, 212, 170),
            key_hover_fill=(45, 116, 168, 220),
            key_hover_edge=(120, 240, 255, 230),
            key_pressed_fill=(45, 142, 64, 210),
            key_pressed_edge=(155, 255, 170, 230),
            key_label=(240, 244, 250, 255),
            key_label_shadow=(0, 0, 0, 220),
            suggestion_fill=(64, 69, 84, 220),
            suggestion_edge=(190, 198, 212, 170),
            suggestion_hover_fill=(58, 94, 147, 220),
            suggestion_hover_edge=(98, 247, 255, 220),
            suggestion_label=(245, 248, 255, 255),
            suggestion_label_shadow=(0, 0, 0, 220),
            swipe_path=(0, 230, 255, 220),
            hover_point_fill=(255, 236, 84, 240),
            hover_point_edge=(30, 30, 30, 220),
            debug_bounds=(255, 80, 255, 255),
            debug_panel_fill=(30, 30, 30, 255),
            debug_panel_edge=(110, 255, 255, 255),
            debug_panel_text=(235, 235, 235, 255),
            badge_shadow=(0, 0, 0, 82),
            badge_fill=(218, 225, 236, 242),
            badge_edge=(105, 118, 137, 230),
            lock_shackle_locked=(72, 83, 98, 255),
            lock_body_locked=(74, 84, 100, 248),
            lock_shackle_unlocked=(56, 130, 182, 255),
            lock_body_unlocked=(54, 120, 170, 248),
        ),
        "light": KeyboardThemePalette(
            theme_id="light",
            label="Light",
            keyboard_body_fill=(242, 244, 247, 235),
            keyboard_body_edge=(145, 154, 170, 210),
            key_fill=(222, 226, 234, 235),
            key_edge=(138, 149, 167, 220),
            key_hover_fill=(183, 214, 241, 235),
            key_hover_edge=(52, 127, 196, 230),
            key_pressed_fill=(168, 218, 180, 235),
            key_pressed_edge=(66, 153, 83, 230),
            key_label=(46, 51, 61, 255),
            key_label_shadow=(255, 255, 255, 220),
            suggestion_fill=(223, 228, 236, 235),
            suggestion_edge=(138, 149, 167, 210),
            suggestion_hover_fill=(189, 218, 246, 235),
            suggestion_hover_edge=(52, 127, 196, 230),
            suggestion_label=(43, 49, 58, 255),
            suggestion_label_shadow=(255, 255, 255, 220),
            swipe_path=(35, 162, 214, 230),
            hover_point_fill=(255, 209, 84, 240),
            hover_point_edge=(65, 65, 65, 220),
            debug_bounds=(194, 76, 194, 255),
            debug_panel_fill=(236, 239, 244, 245),
            debug_panel_edge=(53, 140, 201, 255),
            debug_panel_text=(48, 53, 60, 255),
            badge_shadow=(80, 80, 80, 52),
            badge_fill=(250, 251, 253, 245),
            badge_edge=(126, 138, 154, 220),
            lock_shackle_locked=(104, 116, 130, 255),
            lock_body_locked=(118, 130, 145, 248),
            lock_shackle_unlocked=(52, 127, 196, 255),
            lock_body_unlocked=(72, 147, 216, 248),
        ),
    }

    @classmethod
    def list_options(cls) -> List[Dict[str, str]]:
        return [{"label": palette.label, "value": theme_id} for theme_id, palette in cls._THEMES.items()]

    @classmethod
    def get(cls, theme_id: str) -> KeyboardThemePalette:
        normalized_theme = str(theme_id or "dark").strip().lower()
        return cls._THEMES.get(normalized_theme, cls._THEMES["dark"])
