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
            keyboard_body_fill=(12, 23, 37, 228),
            keyboard_body_edge=(87, 123, 155, 196),
            key_fill=(24, 38, 58, 216),
            key_edge=(95, 128, 158, 165),
            key_hover_fill=(19, 80, 110, 226),
            key_hover_edge=(106, 225, 247, 232),
            key_pressed_fill=(15, 143, 173, 230),
            key_pressed_edge=(152, 244, 255, 236),
            key_label=(241, 247, 255, 255),
            key_label_shadow=(0, 0, 0, 220),
            suggestion_fill=(17, 31, 48, 224),
            suggestion_edge=(86, 116, 145, 176),
            suggestion_hover_fill=(21, 92, 126, 228),
            suggestion_hover_edge=(111, 230, 250, 224),
            suggestion_label=(245, 249, 255, 255),
            suggestion_label_shadow=(0, 0, 0, 220),
            swipe_path=(88, 223, 247, 226),
            hover_point_fill=(255, 220, 115, 244),
            hover_point_edge=(8, 19, 31, 230),
            debug_bounds=(255, 80, 255, 255),
            debug_panel_fill=(10, 18, 30, 248),
            debug_panel_edge=(94, 222, 245, 255),
            debug_panel_text=(236, 244, 255, 255),
            badge_shadow=(4, 10, 18, 92),
            badge_fill=(226, 236, 247, 244),
            badge_edge=(97, 122, 148, 232),
            lock_shackle_locked=(83, 102, 121, 255),
            lock_body_locked=(88, 107, 127, 248),
            lock_shackle_unlocked=(29, 135, 175, 255),
            lock_body_unlocked=(22, 152, 189, 248),
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
