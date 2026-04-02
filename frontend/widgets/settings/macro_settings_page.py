from __future__ import annotations

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

from backend.gesture_remap.rule_overrides import POINT_OVERRIDE_KIND
from backend.macros.macro_step_catalog import STEP_DEFINITIONS
from backend.macros.macro_store import MacroStore
from frontend.widgets.editors.macro_editor_dialog import MacroEditorDialog
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


class MacroSettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._config = None
        self.macro_store = MacroStore()
        self._snapshots_by_name: dict[str, dict] = {}
        self._create_ui()
        self.refresh()

    def _create_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.header = SettingsPageHeader(
            "Macros",
            "Build standalone macros with one trigger gesture and an ordered chain of key, mouse, scroll, and delay steps.",
            parent=self,
        )
        self.create_button = QPushButton("Create Macro")
        set_button_role(self.create_button, "primary")
        set_button_icon(self.create_button, "create")
        self.create_button.clicked.connect(self._on_create_clicked)
        self.header.actions_layout.addStretch()
        self.header.actions_layout.addWidget(self.create_button)
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

    def set_config(self, config):
        self._config = config
        self.refresh()

    def set_macro_store(self, macro_store: MacroStore):
        self.macro_store = macro_store
        self.refresh()

    def snapshot_for(self, name: str) -> dict | None:
        return self._snapshots_by_name.get(name)

    def refresh(self):
        self._snapshots_by_name = {}
        self._clear_cards()

        records = self.macro_store.list_records()
        if not records:
            self.cards_layout.addWidget(
                EmptyStateCard(
                    "No Macros Yet",
                    "Create your first macro to chain keyboard, mouse, and scroll actions behind a custom trigger gesture.",
                    parent=self.cards_container,
                )
            )
            self.cards_layout.addStretch()
            return

        for record in records:
            trigger_label = "3D Hand Model" if record.trigger_kind == POINT_OVERRIDE_KIND else "Rule-Based"
            state_text = "Enabled" if record.enabled else "Disabled"
            self._snapshots_by_name[record.name] = {
                "mode": record.mode.title(),
                "trigger": trigger_label,
                "state": state_text,
            }
            self.cards_layout.addWidget(self._build_macro_card(record, trigger_label, state_text))

        self.cards_layout.addStretch()

    def _clear_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _step_summary(self, record) -> str:
        arrow = "  \u2192  "
        labels = [STEP_DEFINITIONS.get(step.step_type, {}).get("label", step.step_type) for step in record.action_steps]
        if not labels:
            return "No actions"
        if len(labels) <= 3:
            return arrow.join(labels)
        return f"{arrow.join(labels[:3])}{arrow}+{len(labels) - 3} more"

    def _build_macro_card(self, record, trigger_label: str, state_text: str):
        card = SettingsCard(surface="card", parent=self.cards_container)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_label = QLabel(record.name)
        set_label_role(title_label, "card-title")
        title_row.addWidget(title_label)
        title_row.addStretch()
        title_row.addWidget(SettingsBadge(record.mode.title(), "mode", parent=card))
        title_row.addWidget(SettingsBadge(trigger_label, "accent", parent=card))
        title_row.addWidget(SettingsBadge(state_text, "success" if record.enabled else "warning", parent=card))
        card.body_layout.addLayout(title_row)

        summary_label = QLabel(self._step_summary(record))
        summary_label.setWordWrap(True)
        card.body_layout.addWidget(summary_label)

        helper_label = QLabel("Trigger and action chain are edited together. The macro fires once per activation and must disengage before firing again.")
        helper_label.setWordWrap(True)
        set_label_tone(helper_label, "muted")
        card.body_layout.addWidget(helper_label)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 6, 0, 0)
        action_row.setSpacing(8)

        edit_button = QPushButton("Edit")
        set_button_role(edit_button, "primary")
        edit_button.clicked.connect(lambda _checked=False, macro_id=record.id: self._on_edit_clicked(macro_id))
        action_row.addWidget(edit_button)

        duplicate_button = QPushButton("Duplicate")
        set_button_role(duplicate_button, "secondary")
        set_button_icon(duplicate_button, "duplicate")
        duplicate_button.clicked.connect(lambda _checked=False, macro_id=record.id: self._duplicate_macro(macro_id))
        action_row.addWidget(duplicate_button)

        toggle_button = QPushButton("Disable" if record.enabled else "Enable")
        set_button_role(toggle_button, "secondary")
        toggle_button.clicked.connect(lambda _checked=False, macro_id=record.id: self._toggle_macro(macro_id))
        action_row.addWidget(toggle_button)

        delete_button = QPushButton("Delete")
        set_button_role(delete_button, "danger")
        set_button_icon(delete_button, "delete")
        delete_button.clicked.connect(lambda _checked=False, macro_id=record.id: self._delete_macro(macro_id))
        action_row.addWidget(delete_button)
        action_row.addStretch()
        card.body_layout.addLayout(action_row)

        return card

    def _config_source(self):
        return self._config.config if self._config is not None else {}

    def _on_create_clicked(self):
        dialog = MacroEditorDialog(config_source=self._config_source(), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_record is None:
            return
        self.macro_store.upsert(dialog.result_record)
        self.refresh()

    def _on_edit_clicked(self, macro_id: str):
        record = self.macro_store.get(macro_id)
        if record is None:
            return
        dialog = MacroEditorDialog(config_source=self._config_source(), existing_record=record, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_record is None:
            return
        self.macro_store.upsert(dialog.result_record)
        self.refresh()

    def _duplicate_macro(self, macro_id: str):
        record = self.macro_store.get(macro_id)
        if record is None:
            return
        duplicated = type(record).build_new(
            name=f"{record.name} Copy",
            mode=record.mode,
            trigger_kind=record.trigger_kind,
            point_trigger=record.point_trigger,
            rule_trigger=record.rule_trigger,
            action_steps=record.action_steps,
            enabled=record.enabled,
        )
        self.macro_store.upsert(duplicated)
        self.refresh()

    def _toggle_macro(self, macro_id: str):
        record = self.macro_store.get(macro_id)
        if record is None:
            return
        updated = type(record).build_new(
            name=record.name,
            mode=record.mode,
            trigger_kind=record.trigger_kind,
            point_trigger=record.point_trigger,
            rule_trigger=record.rule_trigger,
            action_steps=record.action_steps,
            enabled=not record.enabled,
            macro_id=record.id,
            created_at=record.created_at,
        )
        self.macro_store.upsert(updated)
        self.refresh()

    def _delete_macro(self, macro_id: str):
        record = self.macro_store.get(macro_id)
        if record is None:
            return
        confirm = QMessageBox.question(
            self,
            "Delete Macro",
            f"Delete macro '{record.name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.macro_store.delete(macro_id)
        self.refresh()
