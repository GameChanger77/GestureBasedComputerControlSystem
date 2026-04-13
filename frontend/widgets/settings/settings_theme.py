from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)


_FONT_FAMILY: str | None = None


def _font_path() -> Path:
    return Path(__file__).resolve().parents[2] / "assets" / "fonts" / "Manrope-Variable.ttf"


def _icon_path(name: str) -> Path:
    return Path(__file__).resolve().parents[2] / "assets" / "icons" / name


def ensure_settings_font() -> str:
    global _FONT_FAMILY
    if _FONT_FAMILY is not None:
        return _FONT_FAMILY

    fallback = QApplication.font().family() if QApplication.instance() else "Segoe UI"
    font_file = _font_path()
    if not font_file.exists():
        _FONT_FAMILY = fallback
        return _FONT_FAMILY

    font_id = QFontDatabase.addApplicationFont(str(font_file))
    if font_id < 0:
        _FONT_FAMILY = fallback
        return _FONT_FAMILY

    families = QFontDatabase.applicationFontFamilies(font_id)
    _FONT_FAMILY = families[0] if families else fallback
    return _FONT_FAMILY


def settings_font(size: int = 10, weight: int = QFont.Weight.Medium) -> QFont:
    font = QFont(ensure_settings_font(), size)
    font.setWeight(weight)
    return font


def _stylesheet() -> str:
    checkmark_path = _icon_path("checkmark.svg").as_posix()
    chevron_up_path = _icon_path("chevron-up.svg").as_posix()
    chevron_down_path = _icon_path("chevron-down.svg").as_posix()
    return """
    QWidget[settingsThemeRoot="true"] {
        background-color: #08111f;
        color: #e8eef7;
    }
    QWidget[settingsThemeRoot="true"] QScrollArea,
    QWidget[settingsThemeRoot="true"] QScrollArea > QWidget > QWidget,
    QWidget[settingsThemeRoot="true"] QStackedWidget,
    QWidget[settingsThemeRoot="true"] QWidget[panelRole="page-shell"] {
        background: transparent;
    }
    QWidget[settingsThemeRoot="true"] QLabel[textTone="muted"] {
        color: #93a4bc;
    }
    QWidget[settingsThemeRoot="true"] QLabel[textTone="caption"] {
        color: #7f8ea3;
        font-size: 11px;
    }
    QWidget[settingsThemeRoot="true"] QLabel[textTone="success"] {
        color: #6ee7b7;
    }
    QWidget[settingsThemeRoot="true"] QLabel[textTone="warning"] {
        color: #f8dd88;
    }
    QWidget[settingsThemeRoot="true"] QLabel[textTone="error"] {
        color: #fca5a5;
    }
    QWidget[settingsThemeRoot="true"] QLabel[textRole="page-title"] {
        color: #f8fbff;
        font-size: 23px;
        font-weight: 700;
    }
    QWidget[settingsThemeRoot="true"] QLabel[textRole="section-title"] {
        color: #f5f9ff;
        font-size: 16px;
        font-weight: 650;
    }
    QWidget[settingsThemeRoot="true"] QLabel[textRole="card-title"] {
        color: #f4f8ff;
        font-size: 15px;
        font-weight: 650;
    }
    QWidget[settingsThemeRoot="true"] QLabel[textRole="hero-eyebrow"] {
        color: #7fdff6;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    QWidget[settingsThemeRoot="true"] QLabel[textRole="hero-title"] {
        color: #f8fbff;
        font-size: 28px;
        font-weight: 760;
    }
    QWidget[settingsThemeRoot="true"] QLabel[textRole="hero-subtitle"] {
        color: #94a7c2;
        font-size: 13px;
    }
    QWidget[settingsThemeRoot="true"] QLabel[textRole="metric-value"] {
        color: #f8fbff;
        font-size: 23px;
        font-weight: 760;
    }
    QWidget[settingsThemeRoot="true"] QLabel[textRole="metric-caption"] {
        color: #8fa2bc;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    QWidget[settingsThemeRoot="true"] QLabel[textRole="status-detail"] {
        color: #b2c1d4;
        font-size: 12px;
    }
    QWidget[settingsThemeRoot="true"] QFrame[surface="panel"] {
        background-color: #0f1b2d;
        border: 1px solid #1f3148;
        border-radius: 18px;
    }
    QWidget[settingsThemeRoot="true"] QFrame[surface="card"] {
        background-color: #101d30;
        border: 1px solid #21344d;
        border-radius: 16px;
    }
    QWidget[settingsThemeRoot="true"] QFrame[surface="subtle-card"] {
        background-color: #0d1728;
        border: 1px solid #1a2b41;
        border-radius: 14px;
    }
    QWidget[settingsThemeRoot="true"] QFrame[appRole="shell"] {
        background-color: #08111f;
        border: none;
    }
    QWidget[settingsThemeRoot="true"] QFrame[appRole="hero"] {
        background-color: #0d192b;
        border: 1px solid #1f334b;
        border-radius: 24px;
    }
    QWidget[settingsThemeRoot="true"] QFrame[appRole="toolbar-group"] {
        background-color: #0a1525;
        border: 1px solid #1f3348;
        border-radius: 16px;
    }
    QWidget[settingsThemeRoot="true"] QFrame[appRole="metric-card"] {
        background-color: #0c1627;
        border: 1px solid #21344c;
        border-radius: 16px;
    }
    QWidget[settingsThemeRoot="true"] QFrame[appRole="preview-shell"] {
        background-color: #08121f;
        border: 1px solid #1f3248;
        border-radius: 24px;
    }
    QWidget[settingsThemeRoot="true"] QFrame[appRole="preview-shell"][appState="active"] {
        border-color: #2f7990;
    }
    QWidget[settingsThemeRoot="true"] QFrame[appRole="preview-shell"][appState="waiting"] {
        border-color: #27405d;
    }
    QWidget[settingsThemeRoot="true"] QFrame[appRole="preview-shell"][appState="hidden"] {
        border-color: #415066;
    }
    QWidget[settingsThemeRoot="true"] QFrame[appRole="preview-overlay"] {
        background-color: rgba(8, 18, 31, 214);
        border: 1px solid rgba(101, 159, 196, 0.22);
        border-radius: 18px;
    }
    QWidget[settingsThemeRoot="true"] QLabel[appPreviewRole="overlay-title"] {
        color: #f5f9ff;
        font-size: 19px;
        font-weight: 700;
    }
    QWidget[settingsThemeRoot="true"] QLabel[appPreviewRole="overlay-detail"] {
        color: #95abc7;
        font-size: 12px;
    }
    QWidget[settingsThemeRoot="true"] QListWidget#settingsNavList {
        background-color: #0d1728;
        border: 1px solid #1f3148;
        border-radius: 18px;
        padding: 10px 8px;
        outline: none;
    }
    QWidget[settingsThemeRoot="true"] QListWidget#settingsNavList::item {
        background: transparent;
        border: none;
        border-radius: 12px;
        color: #9fb0c8;
        padding: 11px 12px;
        margin: 3px 0;
    }
    QWidget[settingsThemeRoot="true"] QListWidget#settingsNavList::item:selected {
        background-color: #12314f;
        color: #f8fbff;
    }
    QWidget[settingsThemeRoot="true"] QListWidget#settingsNavList::item:hover:!selected {
        background-color: #112338;
        color: #dce8f7;
    }
    QWidget[settingsThemeRoot="true"] QPushButton {
        background-color: #122236;
        border: 1px solid #27405f;
        border-radius: 11px;
        color: #e5edf7;
        min-height: 36px;
        padding: 0 14px;
    }
    QWidget[settingsThemeRoot="true"] QPushButton:hover {
        background-color: #16304b;
        border-color: #3a6794;
    }
    QWidget[settingsThemeRoot="true"] QPushButton:pressed {
        background-color: #10263d;
    }
    QWidget[settingsThemeRoot="true"] QPushButton:disabled {
        background-color: #0d1624;
        border-color: #1c2a3b;
        color: #5e7088;
    }
    QWidget[settingsThemeRoot="true"] QPushButton[tutorialContinueLocked="true"] {
        background-color: #111924;
        border-color: #243344;
        color: #7a8798;
    }
    QWidget[settingsThemeRoot="true"] QPushButton[tutorialContinueLocked="true"]:hover {
        background-color: #111924;
        border-color: #2b3b4f;
        color: #8694a5;
    }
    QWidget[settingsThemeRoot="true"] QPushButton[tutorialContinueLocked="true"]:pressed {
        background-color: #111924;
        border-color: #243344;
        color: #7a8798;
    }
    QWidget[settingsThemeRoot="true"] QPushButton[role="primary"] {
        background-color: #0ea5c6;
        border-color: #3ad3f7;
        color: #02151b;
        font-weight: 700;
    }
    QWidget[settingsThemeRoot="true"] QPushButton[role="primary"]:hover {
        background-color: #29bbdd;
        border-color: #7de4ff;
    }
    QWidget[settingsThemeRoot="true"] QPushButton[role="secondary"] {
        background-color: #13243a;
    }
    QWidget[settingsThemeRoot="true"] QPushButton[role="ghost"] {
        background-color: transparent;
        border-color: #203349;
        color: #b7c6d8;
    }
    QWidget[settingsThemeRoot="true"] QPushButton[role="danger"] {
        background-color: #3a1620;
        border-color: #7f2d3a;
        color: #ffd6da;
    }
    QWidget[settingsThemeRoot="true"] QPushButton[role="segment"] {
        min-height: 38px;
        padding: 0 18px;
    }
    QWidget[settingsThemeRoot="true"] QPushButton[role="segment"]:checked {
        background-color: #0f8faf;
        border-color: #61d7f2;
        color: #f6fbff;
        font-weight: 700;
    }
    QWidget[settingsThemeRoot="true"] QPushButton[role="toolbar"] {
        min-height: 40px;
        padding: 0 16px;
        border-radius: 13px;
        background-color: #0f1c2e;
        border-color: #26415e;
    }
    QWidget[settingsThemeRoot="true"] QPushButton[role="toolbar"]:hover {
        background-color: #16304b;
        border-color: #3c6d97;
    }
    QWidget[settingsThemeRoot="true"] QToolButton {
        background-color: #112338;
        border: 1px solid #27405f;
        border-radius: 10px;
        color: #dbe8f7;
        min-width: 34px;
        min-height: 34px;
    }
    QWidget[settingsThemeRoot="true"] QToolButton:hover {
        background-color: #18314d;
    }
    QWidget[settingsThemeRoot="true"] QLabel[badgeTone] {
        border-radius: 11px;
        padding: 4px 10px;
        font-size: 11px;
        font-weight: 700;
    }
    QWidget[settingsThemeRoot="true"] QLabel[badgeTone="mode"] {
        background-color: #13243a;
        border: 1px solid #2a4461;
        color: #9fc3ef;
    }
    QWidget[settingsThemeRoot="true"] QLabel[badgeTone="default"] {
        background-color: #152133;
        border: 1px solid #2c3f59;
        color: #9bacc3;
    }
    QWidget[settingsThemeRoot="true"] QLabel[badgeTone="accent"] {
        background-color: #0f3340;
        border: 1px solid #2ba7bf;
        color: #aef2ff;
    }
    QWidget[settingsThemeRoot="true"] QLabel[badgeTone="success"] {
        background-color: #102c24;
        border: 1px solid #228b63;
        color: #82f2c3;
    }
    QWidget[settingsThemeRoot="true"] QLabel[badgeTone="warning"] {
        background-color: #352710;
        border: 1px solid #8c6d1f;
        color: #f8dd88;
    }
    QWidget[settingsThemeRoot="true"] QLabel[badgeTone="danger"] {
        background-color: #34151e;
        border: 1px solid #91435a;
        color: #ffbfd0;
    }
    QWidget[settingsThemeRoot="true"] QLineEdit,
    QWidget[settingsThemeRoot="true"] QComboBox,
    QWidget[settingsThemeRoot="true"] QSpinBox,
    QWidget[settingsThemeRoot="true"] QDoubleSpinBox {
        background-color: #091322;
        border: 1px solid #223750;
        border-radius: 10px;
        min-height: 36px;
        padding: 0 12px;
        selection-background-color: #1f95b0;
    }
    QWidget[settingsThemeRoot="true"] QLineEdit:focus,
    QWidget[settingsThemeRoot="true"] QComboBox:focus,
    QWidget[settingsThemeRoot="true"] QSpinBox:focus,
    QWidget[settingsThemeRoot="true"] QDoubleSpinBox:focus {
        border-color: #63daf4;
    }
    QWidget[settingsThemeRoot="true"] QComboBox::drop-down {
        border: none;
        width: 24px;
    }
    QWidget[settingsThemeRoot="true"] QSpinBox,
    QWidget[settingsThemeRoot="true"] QDoubleSpinBox {
        padding-right: 30px;
    }
    QWidget[settingsThemeRoot="true"] QSpinBox::up-button,
    QWidget[settingsThemeRoot="true"] QDoubleSpinBox::up-button {
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 24px;
        border-left: 1px solid #223750;
        border-bottom: 1px solid #1a2a3d;
        border-top-right-radius: 10px;
        background-color: #101d30;
    }
    QWidget[settingsThemeRoot="true"] QSpinBox::down-button,
    QWidget[settingsThemeRoot="true"] QDoubleSpinBox::down-button {
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 24px;
        border-left: 1px solid #223750;
        border-top: 1px solid #1a2a3d;
        border-bottom-right-radius: 10px;
        background-color: #101d30;
    }
    QWidget[settingsThemeRoot="true"] QSpinBox::up-button:hover,
    QWidget[settingsThemeRoot="true"] QDoubleSpinBox::up-button:hover,
    QWidget[settingsThemeRoot="true"] QSpinBox::down-button:hover,
    QWidget[settingsThemeRoot="true"] QDoubleSpinBox::down-button:hover {
        background-color: #16304b;
    }
    QWidget[settingsThemeRoot="true"] QSpinBox::up-arrow,
    QWidget[settingsThemeRoot="true"] QDoubleSpinBox::up-arrow {
        image: url("__CHEVRON_UP_PATH__");
        width: 12px;
        height: 12px;
    }
    QWidget[settingsThemeRoot="true"] QSpinBox::down-arrow,
    QWidget[settingsThemeRoot="true"] QDoubleSpinBox::down-arrow {
        image: url("__CHEVRON_DOWN_PATH__");
        width: 12px;
        height: 12px;
    }
    QWidget[settingsThemeRoot="true"] QComboBox QAbstractItemView {
        background-color: #0f1b2d;
        color: #e8eef7;
        border: 1px solid #2d4563;
        selection-background-color: #12314f;
    }
    QWidget[settingsThemeRoot="true"] QCheckBox {
        spacing: 8px;
    }
    QWidget[settingsThemeRoot="true"] QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border-radius: 6px;
        border: 1px solid #35506d;
        background: #091322;
    }
    QWidget[settingsThemeRoot="true"] QCheckBox::indicator:checked {
        background: #0ea5c6;
        border-color: #63daf4;
        image: url("__CHECKMARK_PATH__");
    }
    QWidget[settingsThemeRoot="true"] QCheckBox::indicator:hover {
        border-color: #5f86b0;
    }
    QWidget[settingsThemeRoot="true"] QCheckBox::indicator:unchecked:hover {
        background: #0d1c30;
    }
    QWidget[settingsThemeRoot="true"] QSlider {
        min-height: 36px;
    }
    QWidget[settingsThemeRoot="true"] QSlider::groove:horizontal {
        height: 8px;
        border-radius: 4px;
        background: #102132;
        border: 1px solid #21344c;
    }
    QWidget[settingsThemeRoot="true"] QSlider::sub-page:horizontal {
        background: #0ea5c6;
        border-radius: 4px;
    }
    QWidget[settingsThemeRoot="true"] QSlider::add-page:horizontal {
        background: #0b1727;
        border-radius: 4px;
    }
    QWidget[settingsThemeRoot="true"] QSlider::handle:horizontal {
        width: 18px;
        margin: -6px 0;
        border-radius: 9px;
        background: #f4f8ff;
        border: 1px solid #74ddef;
    }
    QWidget[settingsThemeRoot="true"] QSlider::handle:horizontal:hover {
        background: #ffffff;
        border-color: #9be7f5;
    }
    QWidget[settingsThemeRoot="true"] QGroupBox {
        margin-top: 14px;
        padding: 12px 14px 14px 14px;
        border: 1px solid #1d324a;
        border-radius: 15px;
        background-color: #0d1728;
        font-weight: 650;
    }
    QWidget[settingsThemeRoot="true"] QGroupBox QLabel[settingsFormLabel="true"] {
        color: #dce8f7;
    }
    QWidget[settingsThemeRoot="true"] QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: #dff4ff;
    }
    QWidget[settingsThemeRoot="true"] QFrame#settingsDivider {
        background-color: #1e3147;
        max-height: 1px;
    }
    """.replace("__CHECKMARK_PATH__", checkmark_path).replace("__CHEVRON_UP_PATH__", chevron_up_path).replace("__CHEVRON_DOWN_PATH__", chevron_down_path)


def polish_widget(widget: QWidget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def apply_settings_theme(widget: QWidget):
    widget.setProperty("settingsThemeRoot", True)
    widget.setProperty("appThemeRoot", True)
    widget.setFont(settings_font())
    widget.setStyleSheet(_stylesheet())
    polish_widget(widget)


def apply_app_theme(widget: QWidget):
    apply_settings_theme(widget)


def set_button_role(button: QPushButton, role: str):
    button.setProperty("role", role)
    polish_widget(button)


def set_label_tone(label: QLabel, tone: str):
    label.setProperty("textTone", tone)
    polish_widget(label)


def set_label_role(label: QLabel, role: str):
    label.setProperty("textRole", role)
    polish_widget(label)


def standard_icon(widget: QWidget, name: str):
    custom_icon = _icon_path(f"{name}.svg")
    if custom_icon.exists():
        return QIcon(str(custom_icon))

    style = widget.style()
    mapping = {
        "create": QStyle.StandardPixmap.SP_FileDialogNewFolder,
        "save": QStyle.StandardPixmap.SP_DialogSaveButton,
        "reset": QStyle.StandardPixmap.SP_BrowserReload,
        "delete": QStyle.StandardPixmap.SP_TrashIcon,
        "back": QStyle.StandardPixmap.SP_ArrowBack,
        "up": QStyle.StandardPixmap.SP_ArrowUp,
        "down": QStyle.StandardPixmap.SP_ArrowDown,
        "duplicate": QStyle.StandardPixmap.SP_FileDialogNewFolder,
        "play": QStyle.StandardPixmap.SP_MediaPlay,
        "stop": QStyle.StandardPixmap.SP_MediaStop,
        "settings": QStyle.StandardPixmap.SP_FileDialogDetailedView,
        "visibility": QStyle.StandardPixmap.SP_DialogOpenButton,
        "tutorial": QStyle.StandardPixmap.SP_DialogHelpButton,
    }
    pixmap = mapping.get(name)
    if pixmap is None:
        return None
    return style.standardIcon(pixmap)


def set_button_icon(button: QPushButton, name: str):
    icon = standard_icon(button, name)
    if icon is not None:
        button.setIcon(icon)


class SettingsCard(QFrame):
    def __init__(self, *, surface: str = "card", parent=None):
        super().__init__(parent)
        self.setProperty("surface", surface)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 18, 18, 18)
        self._layout.setSpacing(12)

    @property
    def body_layout(self) -> QVBoxLayout:
        return self._layout


class SettingsBadge(QLabel):
    def __init__(self, text: str, tone: str, parent=None):
        super().__init__(text, parent)
        self.setProperty("badgeTone", tone)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        polish_widget(self)

    def set_tone(self, tone: str):
        self.setProperty("badgeTone", tone)
        polish_widget(self)

    def update_badge(self, text: str, tone: str | None = None):
        self.setText(text)
        if tone is not None:
            self.set_tone(tone)


class ToolbarButtonGroup(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("appRole", "toolbar-group")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(10)

    @property
    def body_layout(self) -> QHBoxLayout:
        return self._layout


class MetricCard(QFrame):
    def __init__(self, title: str, value: str = "--", detail: str = "", parent=None):
        super().__init__(parent)
        self.setProperty("appRole", "metric-card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        self.caption_label = QLabel(title)
        set_label_role(self.caption_label, "metric-caption")
        layout.addWidget(self.caption_label)

        self.value_label = QLabel(value)
        set_label_role(self.value_label, "metric-value")
        layout.addWidget(self.value_label)

        self.detail_label = QLabel(detail)
        self.detail_label.setWordWrap(True)
        set_label_role(self.detail_label, "status-detail")
        layout.addWidget(self.detail_label)

    def set_value(self, value: str, *, tone: str | None = None):
        self.value_label.setText(value)
        if tone:
            set_label_tone(self.value_label, tone)
        else:
            self.value_label.setProperty("textTone", None)
            polish_widget(self.value_label)

    def set_detail(self, detail: str):
        self.detail_label.setText(detail)


def animate_opacity(widget: QWidget, *, start: float, end: float, duration: int = 220):
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
    effect.setOpacity(start)
    widget._app_theme_opacity_animation = animation
    animation.start()


class SettingsPageHeader(SettingsCard):
    def __init__(self, title: str, description: str, parent=None):
        super().__init__(surface="panel", parent=parent)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(12)

        copy_layout = QVBoxLayout()
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.setSpacing(8)

        self.title_label = QLabel(title)
        set_label_role(self.title_label, "page-title")
        copy_layout.addWidget(self.title_label)

        self.description_label = QLabel(description)
        self.description_label.setWordWrap(True)
        set_label_tone(self.description_label, "muted")
        copy_layout.addWidget(self.description_label)

        self.actions_layout = QHBoxLayout()
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        self.actions_layout.setSpacing(10)
        header_row.addLayout(copy_layout, 1)
        header_row.addLayout(self.actions_layout, 0)
        self.body_layout.addLayout(header_row)


class EmptyStateCard(SettingsCard):
    def __init__(self, title: str, description: str, parent=None):
        super().__init__(surface="subtle-card", parent=parent)
        title_label = QLabel(title)
        set_label_role(title_label, "section-title")
        self.body_layout.addWidget(title_label)

        description_label = QLabel(description)
        description_label.setWordWrap(True)
        set_label_tone(description_label, "muted")
        self.body_layout.addWidget(description_label)
