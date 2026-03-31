from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.gesture_remap.builtins import BuiltInGestureRegistry
from backend.gesture_remap.override_store import GestureOverrideStore
from backend.gesture_remap.pose_templates import HandPoseTemplate, PoseMatcherConfig
from frontend.widgets.gesture_pose_editor_dialog import GesturePoseEditorDialog


class GestureSettingsPage(QWidget):
    overrides_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.override_store = GestureOverrideStore()
        self._create_ui()
        self.refresh()

    def _create_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        summary = QLabel(
            "Create one custom pose per built-in gesture. Defaults remain available and can be restored at any time."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QHBoxLayout()
        actions.addStretch()
        self.reset_all_button = QPushButton("Reset All To Defaults")
        self.reset_all_button.clicked.connect(self._on_reset_all_clicked)
        actions.addWidget(self.reset_all_button)
        layout.addLayout(actions)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Gesture", "Mode", "State", "Description", "Actions"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

    def set_override_store(self, override_store: GestureOverrideStore):
        self.override_store = override_store
        self.refresh()

    def refresh(self):
        definitions = BuiltInGestureRegistry.all()
        self.table.setRowCount(len(definitions))
        for row, definition in enumerate(definitions):
            override_record = self.override_store.get(definition.id)
            state_text = "Custom" if override_record and override_record.enabled else "Default"

            self.table.setItem(row, 0, QTableWidgetItem(definition.display_name))
            self.table.setItem(row, 1, QTableWidgetItem(definition.mode_label))
            self.table.setItem(row, 2, QTableWidgetItem(state_text))
            description_item = QTableWidgetItem(definition.default_description)
            description_item.setToolTip(definition.default_description)
            self.table.setItem(row, 3, description_item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            action_layout.setSpacing(6)

            edit_label = "Edit Custom" if override_record and override_record.enabled else "Create Custom"
            edit_button = QPushButton(edit_label)
            edit_button.clicked.connect(lambda _checked=False, gesture_id=definition.id: self._on_edit_clicked(gesture_id))
            action_layout.addWidget(edit_button)

            reset_button = QPushButton("Reset")
            reset_button.setEnabled(bool(override_record and override_record.enabled))
            reset_button.clicked.connect(lambda _checked=False, gesture_id=definition.id: self._reset_override(gesture_id))
            action_layout.addWidget(reset_button)
            self.table.setCellWidget(row, 4, action_widget)

        self.reset_all_button.setEnabled(bool(self.override_store.list_records()))

    def _validate_candidate(self, gesture_id, candidate_template, matcher_config):
        other_def, comparison = self.override_store.validate_override(
            BuiltInGestureRegistry,
            gesture_id,
            candidate_template,
            matcher_config,
        )
        if other_def is None:
            return None
        return other_def, comparison

    def _on_edit_clicked(self, gesture_id: str):
        definition = BuiltInGestureRegistry.get(gesture_id)
        override_record = self.override_store.get(gesture_id)
        if override_record and override_record.enabled:
            initial_template = self.override_store.editor_template_for_record(override_record)
        else:
            initial_template = definition.preview_pose_template
        dialog = GesturePoseEditorDialog(
            definition,
            initial_template=initial_template,
            validate_callback=lambda candidate, matcher_config: self._validate_candidate(gesture_id, candidate, matcher_config),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_template is None:
            return

        self.override_store.set_override(
            gesture_id,
            pose_template=dialog.result_template,
            editor_pose_template=dialog.result_template,
            matcher_config=PoseMatcherConfig(),
            enabled=True,
        )
        self.refresh()
        self.overrides_changed.emit()

    def _reset_override(self, gesture_id: str):
        self.override_store.reset_override(gesture_id)
        self.refresh()
        self.overrides_changed.emit()

    def _on_reset_all_clicked(self):
        confirm = QMessageBox.question(
            self,
            "Reset All Gesture Overrides",
            "Reset every custom gesture override back to the built-in defaults?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.override_store.reset_all()
        self.refresh()
        self.overrides_changed.emit()
