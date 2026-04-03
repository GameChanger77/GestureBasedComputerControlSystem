from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from backend.gesture_remap.builtins import BuiltInGestureRegistry
from backend.gesture_remap.override_store import GestureOverrideStore
from backend.gesture_remap.pose_templates import PoseMatcherConfig
from backend.gesture_remap.rule_overrides import RULE_OVERRIDE_KIND
from frontend.widgets.editors.gesture_custom_editor_dialog import GestureCustomEditorDialog
from frontend.widgets.settings.settings_theme import (
    EmptyStateCard,
    SettingsBadge,
    SettingsCard,
    SettingsPageHeader,
    apply_settings_theme,
    set_button_icon,
    set_button_role,
    set_label_role,
    set_label_tone,
)


class GestureSettingsPage(QWidget):
    overrides_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.override_store = GestureOverrideStore()
        self._config = None
        self._snapshots_by_name: dict[str, dict] = {}
        self._create_ui()
        self.refresh()

    def _create_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.header = SettingsPageHeader(
            "Gestures",
            "Customize how built-in gestures are recognized. Each gesture can use either a rule-based recognizer or a 3D hand model recognizer, while the built-in action stays unchanged.",
            parent=self,
        )
        self.reset_all_button = QPushButton("Reset All To Defaults")
        set_button_role(self.reset_all_button, "secondary")
        set_button_icon(self.reset_all_button, "reset")
        self.reset_all_button.clicked.connect(self._on_reset_all_clicked)
        self.header.actions_layout.addStretch()
        self.header.actions_layout.addWidget(self.reset_all_button)
        layout.addWidget(self.header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(2, 2, 2, 2)
        self.cards_layout.setSpacing(14)
        self.scroll_area.setWidget(self.cards_container)
        layout.addWidget(self.scroll_area, 1)

        apply_settings_theme(self)

    def set_override_store(self, override_store: GestureOverrideStore):
        self.override_store = override_store
        self.refresh()

    def set_config(self, config):
        self._config = config
        self.refresh()

    def snapshot_for(self, display_name: str) -> dict | None:
        return self._snapshots_by_name.get(display_name)

    def refresh(self):
        self._snapshots_by_name = {}
        self._clear_cards()

        definitions = BuiltInGestureRegistry.all()
        if not definitions:
            self.cards_layout.addWidget(
                EmptyStateCard(
                    "No Gestures Available",
                    "Built-in gestures could not be loaded for customization.",
                    parent=self.cards_container,
                )
            )
            self.cards_layout.addStretch()
            self.reset_all_button.setEnabled(False)
            return

        current_section = None
        for definition in definitions:
            if definition.section != current_section:
                current_section = definition.section
                section_label = QLabel(current_section)
                set_label_role(section_label, "section-title")
                self.cards_layout.addWidget(section_label)

            override_record = self.override_store.get(definition.id)
            state_text, badge_tone = self._state_for_record(override_record)
            self._snapshots_by_name[definition.display_name] = {
                "mode": definition.mode_label,
                "state": state_text,
            }
            self.cards_layout.addWidget(
                self._build_gesture_card(definition, override_record, state_text, badge_tone)
            )

        self.cards_layout.addStretch()
        self.reset_all_button.setEnabled(bool(self.override_store.list_records()))

    def _clear_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _state_for_record(self, override_record):
        if override_record and override_record.enabled and override_record.is_rule_override:
            return "Custom (Rule-Based)", "accent"
        if override_record and override_record.enabled:
            return "Custom (3D Hand Model)", "success"
        return "Default", "default"

    def _build_gesture_card(self, definition, override_record, state_text: str, badge_tone: str):
        card = SettingsCard(surface="card", parent=self.cards_container)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        title_label = QLabel(definition.display_name)
        set_label_role(title_label, "card-title")
        title_row.addWidget(title_label)
        title_row.addStretch()
        title_row.addWidget(SettingsBadge(definition.mode_label, "mode", parent=card))
        title_row.addWidget(SettingsBadge(state_text, badge_tone, parent=card))
        card.body_layout.addLayout(title_row)

        description = QLabel(definition.default_description)
        description.setWordWrap(True)
        card.body_layout.addWidget(description)

        helper = QLabel("Recognition only. The built-in gesture action and mode behavior remain unchanged.")
        helper.setWordWrap(True)
        set_label_tone(helper, "muted")
        card.body_layout.addWidget(helper)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 6, 0, 0)
        action_row.setSpacing(8)

        edit_button = QPushButton("Edit Custom" if override_record and override_record.enabled else "Create Custom")
        set_button_role(edit_button, "primary")
        set_button_icon(edit_button, "create")
        edit_button.clicked.connect(lambda _checked=False, gesture_id=definition.id: self._on_edit_clicked(gesture_id))
        action_row.addWidget(edit_button)

        reset_button = QPushButton("Reset")
        set_button_role(reset_button, "secondary")
        set_button_icon(reset_button, "reset")
        reset_button.setEnabled(bool(override_record and override_record.enabled))
        reset_button.clicked.connect(lambda _checked=False, gesture_id=definition.id: self._reset_override(gesture_id))
        action_row.addWidget(reset_button)
        action_row.addStretch()
        card.body_layout.addLayout(action_row)

        return card

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
        dialog = GestureCustomEditorDialog(
            definition,
            config_source=self._config.config if self._config is not None else {},
            override_record=override_record,
            validate_callback=lambda candidate, matcher_config: self._validate_candidate(gesture_id, candidate, matcher_config),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if dialog.result_kind == RULE_OVERRIDE_KIND and dialog.result_rule_override is not None:
            self.override_store.set_rule_override(
                gesture_id,
                rule_override=dialog.result_rule_override,
                enabled=True,
            )
        elif dialog.result_template is not None:
            self.override_store.set_override(
                gesture_id,
                pose_template=dialog.result_template,
                editor_pose_template=dialog.result_template,
                matcher_config=PoseMatcherConfig(),
                enabled=True,
            )
        else:
            return
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
