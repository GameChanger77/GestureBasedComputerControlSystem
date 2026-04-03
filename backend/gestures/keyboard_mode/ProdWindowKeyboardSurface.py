from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication

from backend.gestures.GestureUtils import is_hand_fully_open
from backend.gestures.keyboard_mode.KeyboardSurfaceBase import (
    HandFrame,
    KeyboardSurfaceBase,
    SurfaceLayoutState,
)

class ProdWindowKeyboardSurface(KeyboardSurfaceBase):
    _SETTINGS_GROUP = "production_keyboard"
    _SETTINGS_X = "x"
    _SETTINGS_Y = "y"
    _UNLOCK_PENDING_FRAMES = 6

    def __init__(
        self,
        config,
        *,
        flip_x_for_mapping: bool,
        screen_width: int,
        screen_height: int,
    ):
        super().__init__(
            config,
            flip_x_for_mapping=flip_x_for_mapping,
            screen_width=screen_width,
            screen_height=screen_height,
        )
        self.window_width_px = 980
        self.window_height_px = 430
        self.suggestion_band_px = 86
        self.keyboard_padding_x_px = 10
        self.keyboard_padding_bottom_px = 8
        self.follow_alpha = 0.28
        self.open_extension_threshold = float(config.get("finger_extension_angle", 155.0))
        self._window_locked = True
        self._unlock_pending_frames = 0
        self._screen_origin_x_px = 0.0
        self._screen_origin_y_px = 0.0
        self._screen_width_px = float(self.screen_width)
        self._screen_height_px = float(self.screen_height)

        self._refresh_primary_screen_geometry()

        self._window_x_px, self._window_y_px = self._load_or_center_position()
        self._last_follow_center_px: Optional[Tuple[float, float]] = None

    def _refresh_primary_screen_geometry(self):
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self._screen_origin_x_px = 0.0
            self._screen_origin_y_px = 0.0
            self._screen_width_px = float(self.screen_width)
            self._screen_height_px = float(self.screen_height)
            return

        geom = screen.availableGeometry()
        self._screen_origin_x_px = float(geom.x())
        self._screen_origin_y_px = float(geom.y())
        self._screen_width_px = max(1.0, float(geom.width()))
        self._screen_height_px = max(1.0, float(geom.height()))

    def _load_or_center_position(self) -> Tuple[float, float]:
        settings = QSettings("GBCCS", "HandGestureControl")
        settings.beginGroup(self._SETTINGS_GROUP)
        x_val = settings.value(self._SETTINGS_X, None)
        y_val = settings.value(self._SETTINGS_Y, None)
        settings.endGroup()

        if x_val is None or y_val is None:
            return self._center_position()

        try:
            x_px = float(x_val)
            y_px = float(y_val)
        except (TypeError, ValueError):
            return self._center_position()

        return self._clamp_window_position(x_px, y_px)

    def _center_position(self) -> Tuple[float, float]:
        x = self._screen_origin_x_px + ((self._screen_width_px - self.window_width_px) / 2.0)
        y = self._screen_origin_y_px + ((self._screen_height_px - self.window_height_px) / 2.0)
        return self._clamp_window_position(x, y)

    def _clamp_window_position(self, x_px: float, y_px: float) -> Tuple[float, float]:
        min_x = self._screen_origin_x_px
        min_y = self._screen_origin_y_px
        max_x = self._screen_origin_x_px + max(0.0, self._screen_width_px - self.window_width_px)
        max_y = self._screen_origin_y_px + max(0.0, self._screen_height_px - self.window_height_px)
        return (
            self._clamp(x_px, min_x, max_x),
            self._clamp(y_px, min_y, max_y),
        )

    def _save_position(self):
        settings = QSettings("GBCCS", "HandGestureControl")
        settings.beginGroup(self._SETTINGS_GROUP)
        settings.setValue(self._SETTINGS_X, int(round(self._window_x_px)))
        settings.setValue(self._SETTINGS_Y, int(round(self._window_y_px)))
        settings.endGroup()

    def _right_anchor_screen_px(self, hands_data) -> Optional[Tuple[float, float]]:
        if not hands_data.camera.has_right:
            return None
        right = hands_data.camera.right
        if right is None or not right.exists:
            return None

        anchor = right.index.tip
        if anchor is None:
            anchor = right.wrist
        if anchor is None:
            return None

        nx = float(anchor[0])
        ny = float(anchor[1])
        if self.flip_x_for_mapping:
            nx = 1.0 - nx

        return (
            self._screen_origin_x_px + (nx * self._screen_width_px),
            self._screen_origin_y_px + (ny * self._screen_height_px),
        )

    def _right_open_for_drag(self, hands_data) -> bool:
        if not hands_data.wrist.has_right:
            return False
        right = hands_data.wrist.right
        if right is None or not right.exists:
            return False
        return is_hand_fully_open(
            right,
            extension_threshold=self.open_extension_threshold,
            min_extended_fingers=4,
            openness_threshold=0.08,
        )

    def _update_window_follow(self, hands_data):
        right_open = self._right_open_for_drag(hands_data)
        anchor = self._right_anchor_screen_px(hands_data)
        was_locked = self._window_locked

        if right_open and anchor is not None:
            self._unlock_pending_frames = min(
                self._unlock_pending_frames + 1,
                self._UNLOCK_PENDING_FRAMES,
            )

            if self._window_locked and self._unlock_pending_frames >= self._UNLOCK_PENDING_FRAMES:
                self._window_locked = False

            if not self._window_locked:
                if self._last_follow_center_px is None:
                    follow_center = anchor
                else:
                    lx, ly = self._last_follow_center_px
                    follow_center = (
                        (lx * (1.0 - self.follow_alpha)) + (anchor[0] * self.follow_alpha),
                        (ly * (1.0 - self.follow_alpha)) + (anchor[1] * self.follow_alpha),
                    )
                self._last_follow_center_px = follow_center

                next_x = follow_center[0] - (self.window_width_px / 2.0)
                next_y = follow_center[1] - (self.window_height_px / 2.0)
                self._window_x_px, self._window_y_px = self._clamp_window_position(next_x, next_y)
        else:
            self._unlock_pending_frames = 0
            self._window_locked = True
            self._last_follow_center_px = None

        if was_locked is False and self._window_locked is True:
            self._save_position()

    def _window_frame_normalized(self) -> HandFrame:
        left = (self._window_x_px - self._screen_origin_x_px) / self._screen_width_px
        top = (self._window_y_px - self._screen_origin_y_px) / self._screen_height_px
        width = self.window_width_px / self._screen_width_px
        height = self.window_height_px / self._screen_height_px
        return HandFrame(left=left, top=top, width=width, height=height)

    def _keyboard_frame_normalized(self) -> HandFrame:
        left_px = self._window_x_px + self.keyboard_padding_x_px
        top_px = self._window_y_px + self.suggestion_band_px
        width_px = max(120.0, self.window_width_px - (2.0 * self.keyboard_padding_x_px))
        height_px = max(120.0, self.window_height_px - self.suggestion_band_px - self.keyboard_padding_bottom_px)
        return HandFrame(
            left=(left_px - self._screen_origin_x_px) / self._screen_width_px,
            top=(top_px - self._screen_origin_y_px) / self._screen_height_px,
            width=width_px / self._screen_width_px,
            height=height_px / self._screen_height_px,
        )

    def update_layout(self, hands_data, *, paused: bool, rows: List[List[Dict[str, object]]]) -> SurfaceLayoutState:
        self._refresh_primary_screen_geometry()
        self._window_x_px, self._window_y_px = self._clamp_window_position(self._window_x_px, self._window_y_px)
        self._update_window_follow(hands_data)
        window_frame = self._window_frame_normalized()
        keyboard_frame = self._keyboard_frame_normalized()
        overlay_keys = self._build_overlay_keys(rows, keyboard_frame)

        return SurfaceLayoutState(
            active_frames={"left": None, "right": None},
            unified_frame=keyboard_frame,
            overlay_keys=overlay_keys,
            drag_bounds_by_side={},
            extra_overlay={
                "surface": "prod",
                "prod_window_locked": self._window_locked,
                "prod_window_rect_px": {
                    "x": int(round(self._window_x_px)),
                    "y": int(round(self._window_y_px)),
                    "w": int(self.window_width_px),
                    "h": int(self.window_height_px),
                },
                "prod_window_rect_norm": {
                    "x": window_frame.left,
                    "y": window_frame.top,
                    "w": window_frame.width,
                    "h": window_frame.height,
                },
                "prod_keyboard_rect_norm": {
                    "x": keyboard_frame.left,
                    "y": keyboard_frame.top,
                    "w": keyboard_frame.width,
                    "h": keyboard_frame.height,
                },
                "prod_screen_size": {
                    "x": int(round(self._screen_origin_x_px)),
                    "y": int(round(self._screen_origin_y_px)),
                    "w": int(round(self._screen_width_px)),
                    "h": int(round(self._screen_height_px)),
                },
            },
        )

    def shutdown(self):
        self._save_position()
