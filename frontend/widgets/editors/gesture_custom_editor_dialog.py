from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
)

from backend.gesture_remap.rule_overrides import RULE_OVERRIDE_KIND
from frontend.widgets.editors.dialog_windowing import (
    apply_bounded_dialog_geometry,
    configure_bounded_dialog_window,
    ensure_bounded_dialog_screen_tracking,
)
from frontend.widgets.editors.gesture_pose_editor_dialog import GesturePoseEditorWidget
from frontend.widgets.editors.gesture_rule_editor_widget import GestureRuleEditorWidget
from frontend.widgets.settings.settings_theme import (
    SettingsCard,
    SettingsPageHeader,
    apply_settings_theme,
    set_button_role,
)


class GestureCustomEditorDialog(QDialog):
    def __init__(
        self,
        gesture_definition,
        config_source,
        override_record=None,
        validate_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self.gesture_definition = gesture_definition
        self.override_record = override_record
        self.result_kind: str | None = None
        self.result_template = None
        self.result_rule_override = None

        if override_record and override_record.enabled and override_record.is_point_override:
            initial_point_template = override_record.editor_pose_template or override_record.pose_template
            initial_kind = "point"
        else:
            initial_point_template = gesture_definition.preview_pose_template
            initial_kind = "rule"

        if override_record and override_record.enabled and override_record.is_rule_override:
            initial_rule_override = override_record.rule_override
            initial_kind = RULE_OVERRIDE_KIND
        else:
            initial_rule_override = gesture_definition.build_default_rule_override(config_source)
        default_rule_override = gesture_definition.build_default_rule_override(config_source)

        self.setWindowTitle(f"Custom Gesture: {gesture_definition.display_name}")
        configure_bounded_dialog_window(
            self,
            default_size=QSize(1120, 760),
            min_size=QSize(900, 640),
            parent=parent,
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        content_scroll = QScrollArea(self)
        content_scroll.setWidgetResizable(True)
        content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_container = QFrame(self)
        content_root = QVBoxLayout(content_container)
        content_root.setContentsMargins(0, 0, 0, 0)
        content_root.setSpacing(14)

        header = SettingsPageHeader(
            gesture_definition.display_name,
            "Choose one custom recognizer for this gesture. Rule-based and 3D hand model overrides are mutually exclusive.",
            parent=self,
        )
        content_root.addWidget(header)

        toggle_card = SettingsCard(surface="subtle-card", parent=self)
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(6)
        self.rule_button = QPushButton("Rule-Based")
        self.rule_button.setCheckable(True)
        set_button_role(self.rule_button, "segment")
        self.rule_button.clicked.connect(lambda: self._set_selected_kind(RULE_OVERRIDE_KIND))
        toggle_row.addWidget(self.rule_button)
        self.point_button = QPushButton("3D Hand Model")
        self.point_button.setCheckable(True)
        set_button_role(self.point_button, "segment")
        self.point_button.clicked.connect(lambda: self._set_selected_kind("point"))
        toggle_row.addWidget(self.point_button)
        toggle_row.addStretch()
        toggle_card.body_layout.addLayout(toggle_row)
        content_root.addWidget(toggle_card)

        content_card = SettingsCard(surface="panel", parent=self)
        self.page_stack = QStackedWidget()
        self.rule_editor = GestureRuleEditorWidget(
            gesture_definition,
            initial_rule_override=initial_rule_override,
            default_rule_override=default_rule_override,
            parent=self,
        )
        self.point_editor = GesturePoseEditorWidget(
            gesture_definition,
            initial_template=initial_point_template,
            validate_callback=validate_callback,
            parent=self,
        )
        self.point_editor_scroll = QScrollArea(self)
        self.point_editor_scroll.setWidgetResizable(True)
        self.point_editor_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.point_editor_scroll.setWidget(self.point_editor)
        self.page_stack.addWidget(self.rule_editor)
        self.page_stack.addWidget(self.point_editor_scroll)
        content_card.body_layout.addWidget(self.page_stack, 1)
        content_root.addWidget(content_card, 1)

        content_scroll.setWidget(content_container)
        root.addWidget(content_scroll, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.save_button = QPushButton("Save")
        set_button_role(self.save_button, "primary")
        self.save_button.clicked.connect(self._on_save_clicked)
        button_row.addWidget(self.save_button)
        cancel_button = QPushButton("Cancel")
        set_button_role(cancel_button, "secondary")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)
        root.addLayout(button_row)

        self.rule_editor.can_save_changed.connect(self._refresh_save_button)
        self.point_editor.can_save_changed.connect(self._refresh_save_button)
        self._set_selected_kind(initial_kind)
        apply_settings_theme(self)

    def showEvent(self, event):
        super().showEvent(event)
        ensure_bounded_dialog_screen_tracking(self)
        apply_bounded_dialog_geometry(self, center=False)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            apply_bounded_dialog_geometry(self, center=False)

    def selected_kind(self) -> str:
        return RULE_OVERRIDE_KIND if self.rule_button.isChecked() else "point"

    def _set_selected_kind(self, kind: str):
        is_rule = kind == RULE_OVERRIDE_KIND
        self.rule_button.setChecked(is_rule)
        self.point_button.setChecked(not is_rule)
        self.page_stack.setCurrentWidget(self.rule_editor if is_rule else self.point_editor_scroll)
        self._refresh_toggle_styles()
        self._refresh_save_button()

    def _refresh_toggle_styles(self):
        return

    def _refresh_save_button(self, *_args):
        if self.selected_kind() == RULE_OVERRIDE_KIND:
            self.save_button.setEnabled(self.rule_editor.can_save)
        else:
            self.save_button.setEnabled(self.point_editor.can_save)

    def _on_save_clicked(self):
        if self.selected_kind() == RULE_OVERRIDE_KIND:
            self.result_kind = RULE_OVERRIDE_KIND
            self.result_rule_override = self.rule_editor.build_rule_override()
            self.result_template = None
        else:
            self.result_kind = "point"
            self.result_template = self.point_editor.build_result_template()
            self.result_rule_override = None
        self.accept()
