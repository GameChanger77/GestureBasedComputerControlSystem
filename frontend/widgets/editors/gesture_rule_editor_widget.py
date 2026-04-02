from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QFormLayout,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from backend.custom_rules.condition_catalog import CONDITION_DEFINITIONS
from backend.gesture_remap.rule_overrides import GestureRuleOverride
from frontend.widgets.settings.settings_theme import (
    SettingsCard,
    apply_settings_theme,
    set_button_icon,
    set_button_role,
    set_label_role,
    set_label_tone,
)


class RuleConditionEditor(SettingsCard):
    changed = Signal()
    remove_requested = Signal(QWidget)

    def __init__(self, condition: dict | None = None, parent=None):
        super().__init__(surface="subtle-card", parent=parent)
        self._field_widgets = {}
        self._field_layout = None
        self._condition_data = dict(condition or {})
        self._create_ui()
        initial_op = self._condition_data.get("op")
        if initial_op in CONDITION_DEFINITIONS:
            self.op_combo.setCurrentIndex(self.op_combo.findData(initial_op))
        self._rebuild_fields()

    def _create_ui(self):
        root = self.body_layout

        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(QLabel("Condition"))
        self.op_combo = QComboBox()
        for op, definition in CONDITION_DEFINITIONS.items():
            self.op_combo.addItem(definition["label"], op)
        self.op_combo.currentIndexChanged.connect(self._rebuild_fields)
        header.addWidget(self.op_combo, 1)
        remove_button = QPushButton("Remove")
        set_button_role(remove_button, "danger")
        remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        header.addWidget(remove_button)
        root.addLayout(header)

        self._field_layout = QFormLayout()
        self._field_layout.setContentsMargins(0, 0, 0, 0)
        self._field_layout.setSpacing(6)
        root.addLayout(self._field_layout)

    def _rebuild_fields(self):
        while self._field_layout.rowCount():
            self._field_layout.removeRow(0)
        self._field_widgets = {}

        op = self.current_op()
        definition = CONDITION_DEFINITIONS[op]
        for field in definition["fields"]:
            widget = self._build_field_widget(field, self._condition_data.get(field["name"], field.get("default")))
            self._field_widgets[field["name"]] = (field, widget)
            self._field_layout.addRow(field["label"], widget)
        self.changed.emit()

    def _build_field_widget(self, field: dict, value):
        field_type = field["type"]
        if field_type == "enum":
            combo = QComboBox()
            for option_value, option_label in field.get("options", []):
                combo.addItem(option_label, option_value)
            index = combo.findData(value)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.currentIndexChanged.connect(self.changed.emit)
            return combo

        if field_type == "multi_enum":
            container = QWidget()
            layout = QGridLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setHorizontalSpacing(8)
            layout.setVerticalSpacing(4)
            selected_values = {str(item) for item in (value or [])}
            checkboxes = {}
            for idx, (option_value, option_label) in enumerate(field.get("options", [])):
                checkbox = QCheckBox(option_label)
                checkbox.setChecked(option_value in selected_values)
                checkbox.toggled.connect(self.changed.emit)
                layout.addWidget(checkbox, idx // 2, idx % 2)
                checkboxes[option_value] = checkbox
            container._multi_checkboxes = checkboxes
            return container

        if field_type == "bool":
            checkbox = QCheckBox()
            checkbox.setChecked(bool(value))
            checkbox.toggled.connect(self.changed.emit)
            return checkbox

        if field_type == "int":
            spinbox = QSpinBox()
            spinbox.setRange(int(field.get("min", -1_000_000)), int(field.get("max", 1_000_000)))
            spinbox.setSingleStep(int(field.get("step", 1)))
            spinbox.setValue(int(value))
            spinbox.valueChanged.connect(self.changed.emit)
            return spinbox

        if field_type == "float":
            spinbox = QDoubleSpinBox()
            spinbox.setRange(float(field.get("min", -1_000_000.0)), float(field.get("max", 1_000_000.0)))
            spinbox.setSingleStep(float(field.get("step", 0.1)))
            spinbox.setDecimals(int(field.get("decimals", 3)))
            spinbox.setValue(float(value))
            spinbox.valueChanged.connect(self.changed.emit)
            return spinbox

        raise ValueError(f"Unsupported rule condition field type '{field_type}'")

    def current_op(self) -> str:
        return str(self.op_combo.currentData())

    def to_condition(self) -> dict:
        condition = {"op": self.current_op()}
        for field_name, (field, widget) in self._field_widgets.items():
            field_type = field["type"]
            if field_type == "enum":
                condition[field_name] = widget.currentData()
            elif field_type == "multi_enum":
                condition[field_name] = [
                    value
                    for value, checkbox in widget._multi_checkboxes.items()
                    if checkbox.isChecked()
                ]
            elif field_type == "bool":
                condition[field_name] = bool(widget.isChecked())
            elif field_type == "int":
                condition[field_name] = int(widget.value())
            elif field_type == "float":
                condition[field_name] = float(widget.value())
        return condition


class GestureRuleEditorWidget(QWidget):
    can_save_changed = Signal(bool)

    def __init__(
        self,
        gesture_definition=None,
        initial_rule_override: GestureRuleOverride | None = None,
        default_rule_override: GestureRuleOverride | None = None,
        title_html: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        if initial_rule_override is None:
            raise ValueError("initial_rule_override is required")
        self.gesture_definition = gesture_definition
        self._title_html = title_html
        self._default_rule_override = default_rule_override or initial_rule_override
        self._condition_editors: list[RuleConditionEditor] = []
        self._can_save = False
        self._create_ui()
        self.load_rule_override(initial_rule_override)
        apply_settings_theme(self)

    @property
    def can_save(self) -> bool:
        return self._can_save

    def load_rule_override(self, rule_override: GestureRuleOverride):
        while self._condition_editors:
            self._remove_condition_editor(self._condition_editors[0])
        for condition in rule_override.conditions:
            self._add_condition_editor(condition)
        self.pending_frames_spinbox.setValue(int(rule_override.pending_frames))
        self.ending_frames_spinbox.setValue(int(rule_override.ending_frames))
        self._refresh_status()

    def build_rule_override(self) -> GestureRuleOverride:
        return GestureRuleOverride.from_dict(
            {
                "conditions": [editor.to_condition() for editor in self._condition_editors],
                "confirm": {
                    "pending_frames": int(self.pending_frames_spinbox.value()),
                    "ending_frames": int(self.ending_frames_spinbox.value()),
                },
            }
        )

    def _create_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        if self._title_html is not None:
            label_text = self._title_html
        else:
            label_text = (
                f"<b>{self.gesture_definition.display_name}</b><br>"
                f"Mode: {self.gesture_definition.mode_label}<br>"
                f"{self.gesture_definition.default_description}<br>"
                "This editor changes how the gesture is detected. The gesture's built-in action does not change."
            )
        if label_text:
            context_card = SettingsCard(surface="subtle-card", parent=self)
            context_label = QLabel(label_text)
            context_label.setWordWrap(True)
            context_card.body_layout.addWidget(context_label)
            root.addWidget(context_card)

        debounce_group = QGroupBox("Confirmation")
        debounce_layout = QFormLayout(debounce_group)
        self.pending_frames_spinbox = QSpinBox()
        self.pending_frames_spinbox.setRange(1, 60)
        self.pending_frames_spinbox.valueChanged.connect(self._refresh_status)
        debounce_layout.addRow("Pending Frames", self.pending_frames_spinbox)
        self.ending_frames_spinbox = QSpinBox()
        self.ending_frames_spinbox.setRange(1, 60)
        self.ending_frames_spinbox.valueChanged.connect(self._refresh_status)
        debounce_layout.addRow("Ending Frames", self.ending_frames_spinbox)
        root.addWidget(debounce_group)

        actions_row = QHBoxLayout()
        add_button = QPushButton("Add Condition")
        set_button_role(add_button, "primary")
        set_button_icon(add_button, "create")
        add_button.clicked.connect(lambda: self._add_condition_editor())
        actions_row.addWidget(add_button)
        restore_button = QPushButton("Restore Built-In Rule")
        set_button_role(restore_button, "secondary")
        set_button_icon(restore_button, "reset")
        restore_button.clicked.connect(self._restore_default_rule)
        actions_row.addWidget(restore_button)
        actions_row.addStretch()
        root.addLayout(actions_row)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self.conditions_layout = QVBoxLayout(container)
        self.conditions_layout.setContentsMargins(0, 0, 0, 0)
        self.conditions_layout.setSpacing(8)
        self.conditions_layout.addStretch()
        scroll_area.setWidget(container)
        root.addWidget(scroll_area, 1)

    def _add_condition_editor(self, condition: dict | None = None):
        editor = RuleConditionEditor(condition=condition, parent=self)
        editor.changed.connect(self._refresh_status)
        editor.remove_requested.connect(self._remove_condition_editor)
        self._condition_editors.append(editor)
        self.conditions_layout.insertWidget(self.conditions_layout.count() - 1, editor)
        self._refresh_status()

    def _remove_condition_editor(self, editor: QWidget):
        if editor in self._condition_editors:
            self._condition_editors.remove(editor)
        self.conditions_layout.removeWidget(editor)
        editor.deleteLater()
        self._refresh_status()

    def _restore_default_rule(self):
        self.load_rule_override(self._default_rule_override)

    def _refresh_status(self):
        can_save = len(self._condition_editors) > 0
        validation_error = None
        if can_save:
            try:
                self.build_rule_override()
            except Exception as exc:
                can_save = False
                validation_error = str(exc)
        if can_save:
            self.status_label.setText(
                f"{len(self._condition_editors)} condition(s) configured. "
                "The built-in gesture action will keep its current behavior."
            )
            set_label_tone(self.status_label, "success")
        elif validation_error:
            self.status_label.setText(f"Rule is incomplete: {validation_error}")
            set_label_tone(self.status_label, "error")
        else:
            self.status_label.setText("Add at least one condition to define a rule-based override.")
            set_label_tone(self.status_label, "muted")

        if self._can_save != can_save:
            self._can_save = can_save
            self.can_save_changed.emit(can_save)
