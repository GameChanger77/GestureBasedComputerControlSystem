from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QWidget


def _screen_geometry_for(widget: QWidget | None) -> QRect:
    if widget is not None and widget.windowHandle() is not None and widget.windowHandle().screen() is not None:
        return widget.windowHandle().screen().availableGeometry()

    if widget is not None:
        window_handle = widget.window().windowHandle() if widget.window() is not None else None
        if window_handle is not None and window_handle.screen() is not None:
            return window_handle.screen().availableGeometry()

    app = QGuiApplication.instance()
    if app is not None:
        screen = app.primaryScreen()
        if screen is not None:
            return screen.availableGeometry()

    return QRect(100, 100, 1440, 900)


def configure_bounded_dialog_window(
    dialog: QDialog,
    *,
    default_size: QSize,
    min_size: QSize,
    parent: QWidget | None = None,
) -> None:
    dialog.setWindowFlag(Qt.Window, True)
    dialog.setWindowFlag(Qt.WindowCloseButtonHint, True)
    dialog.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
    dialog.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
    dialog.setSizeGripEnabled(True)
    dialog._bounded_dialog_default_size = QSize(default_size)
    dialog._bounded_dialog_min_size = QSize(min_size)
    dialog._bounded_dialog_parent = parent
    dialog._bounded_dialog_screen_connected = False
    apply_bounded_dialog_geometry(dialog, center=True)


def apply_bounded_dialog_geometry(dialog: QDialog, *, center: bool = False) -> None:
    default_size = QSize(getattr(dialog, "_bounded_dialog_default_size", QSize(1100, 760)))
    min_size = QSize(getattr(dialog, "_bounded_dialog_min_size", QSize(860, 620)))
    parent = getattr(dialog, "_bounded_dialog_parent", None)
    geometry = _screen_geometry_for(dialog if dialog.windowHandle() is not None else parent or dialog.parentWidget())

    effective_min_width = min(min_size.width(), geometry.width())
    effective_min_height = min(min_size.height(), geometry.height())
    max_width = max(effective_min_width, geometry.width())
    max_height = max(effective_min_height, geometry.height())

    dialog.setMinimumSize(QSize(effective_min_width, effective_min_height))
    dialog.setMaximumSize(QSize(max_width, max_height))

    bounded_width = max(effective_min_width, min(dialog.width() or default_size.width(), max_width))
    bounded_height = max(effective_min_height, min(dialog.height() or default_size.height(), max_height))
    dialog.resize(bounded_width, bounded_height)

    current_x = dialog.x()
    current_y = dialog.y()
    if center:
        top_left = geometry.center() - QPoint(bounded_width // 2, bounded_height // 2)
        current_x = top_left.x()
        current_y = top_left.y()

    clamped_x = max(geometry.left(), min(current_x, geometry.right() - bounded_width + 1))
    clamped_y = max(geometry.top(), min(current_y, geometry.bottom() - bounded_height + 1))
    dialog.move(clamped_x, clamped_y)


def ensure_bounded_dialog_screen_tracking(dialog: QDialog) -> None:
    if getattr(dialog, "_bounded_dialog_screen_connected", False):
        return
    handle = dialog.windowHandle()
    if handle is None:
        return
    handle.screenChanged.connect(lambda _screen: apply_bounded_dialog_geometry(dialog, center=False))
    dialog._bounded_dialog_screen_connected = True
